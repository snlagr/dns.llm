#!/usr/bin/env python3
import os
import sys
import time
import threading
import datetime
import httpx
from dnslib import RR, TXT, QTYPE, RCODE
from dnslib.server import DNSServer, BaseResolver, DNSLogger

CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN  = os.environ["CF_API_TOKEN"]
MODEL         = "@cf/meta/llama-3.2-1b-instruct"
CF_URL        = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{MODEL}"

SYSTEM_PROMPT = "Answer in short, english, no markdown or newlines"

RATE_LIMIT  = 10   # max queries per window per source IP
RATE_WINDOW = 60   # seconds

LOG_PATH = "/var/log/dns-llm/queries.log"

_buckets: dict[str, tuple[float, int]] = {}
_buckets_lock = threading.Lock()
_log_lock = threading.Lock()


def log_query(src_ip: str, status: str, query: str) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    line = f"{ts}\t{src_ip}\t{status}\t{query}\n"
    try:
        with _log_lock, open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def rate_limited(src_ip: str) -> bool:
    now = time.time()
    with _buckets_lock:
        if len(_buckets) > 10000:
            for ip in [ip for ip, (start, _) in _buckets.items() if now - start >= RATE_WINDOW]:
                del _buckets[ip]
        start, count = _buckets.get(src_ip, (now, 0))
        if now - start >= RATE_WINDOW:
            start, count = now, 0
        count += 1
        _buckets[src_ip] = (start, count)
        return count > RATE_LIMIT


def ask_llm(prompt: str) -> str:
    r = httpx.post(
        CF_URL,
        headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
        json={
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": 200,
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["result"]["response"].strip()


def to_txt_chunks(text: str, size: int = 255) -> list[bytes]:
    return [text[i : i + size].encode() for i in range(0, len(text), size)]


class LLMResolver(BaseResolver):
    def resolve(self, request, handler):
        reply   = request.reply()
        qname   = request.q.qname
        src_ip  = handler.client_address[0]
        labels  = str(qname).rstrip(".").split(".")
        prompt  = " ".join(labels)

        if rate_limited(src_ip):
            log_query(src_ip, "refused", prompt)
            reply.header.rcode = RCODE.REFUSED
            return reply

        try:
            answer = ask_llm(prompt)
            log_query(src_ip, "ok", prompt)
            for chunk in to_txt_chunks(answer):
                reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT([chunk])))
        except Exception as e:
            log_query(src_ip, "error", prompt)
            reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT([f"error: {e}".encode()])))

        return reply


if __name__ == "__main__":
    port   = int(sys.argv[1]) if len(sys.argv) > 1 else 5353
    server = DNSServer(LLMResolver(), port=port, address="0.0.0.0", logger=DNSLogger("-"))
    print(f"listening on 0.0.0.0:{port}")
    print(f"try:  dig what.is.the.capital.of.france TXT @127.0.0.1 -p {port}")
    server.start()
