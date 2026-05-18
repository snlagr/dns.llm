#!/usr/bin/env python3
import os
import sys
import httpx
from dnslib import RR, TXT, QTYPE
from dnslib.server import DNSServer, BaseResolver, DNSLogger

CF_ACCOUNT_ID = os.environ["CF_ACCOUNT_ID"]
CF_API_TOKEN  = os.environ["CF_API_TOKEN"]
MODEL         = "@cf/meta/llama-3.2-1b-instruct"
CF_URL        = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{MODEL}"

SYSTEM_PROMPT = "Answer in short english"


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
        reply  = request.reply()
        qname  = request.q.qname
        labels = str(qname).rstrip(".").split(".")
        prompt = " ".join(labels)

        print(f"query: {prompt!r}")

        try:
            answer = ask_llm(prompt)
            print(f"answer: {answer!r}")
            for chunk in to_txt_chunks(answer):
                reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT([chunk])))
        except Exception as e:
            reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT([f"error: {e}".encode()])))

        return reply


if __name__ == "__main__":
    port   = int(sys.argv[1]) if len(sys.argv) > 1 else 5353
    server = DNSServer(LLMResolver(), port=port, address="127.0.0.1", logger=DNSLogger("-"))
    print(f"listening on 127.0.0.1:{port}")
    print(f"try:  dig what.is.the.capital.of.france TXT @127.0.0.1 -p {port}")
    server.start()
