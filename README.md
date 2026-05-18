# dns-llm

Ask a language model over plain DNS. Inspired by [dns.toys](https://github.com/knadh/dns.toys).

Encode your question as a chain of DNS labels, send a TXT query to `ask.sonal.dev`, and the answer comes back as TXT records. No HTTP, no API key, no JavaScript. Just `dig`.

## Try it

```
dig +short what.is.the.capital.of.france @ask.sonal.dev
"The capital of France is Paris."

dig +short why.is.the.sky.blue @ask.sonal.dev
"Rayleigh scattering: shorter blue wavelengths scatter more in the atmosphere."
```

## How it works

1. The query name is split on dots and rejoined with spaces — that becomes the prompt.
2. The prompt is sent to [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/) (`llama-3.2-1b-instruct`).
3. The response is chunked into 255-byte TXT records and returned as the DNS answer.

## Rules of the game

- Each DNS label is capped at 63 characters — longer words must be split.
- The full query name is capped at 253 characters, so keep prompts short.
- Answers are truncated to ~200 tokens. This is a toy, not a chatbot.
- No memory between queries. Each `dig` is independent.

## Source

The whole thing is ~60 lines of Python using `dnslib` and `httpx`. The interesting trick is in the resolver:

```python
labels = str(qname).rstrip(".").split(".")
prompt = " ".join(labels)
answer = ask_llm(prompt)
for chunk in to_txt_chunks(answer):
    reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT([chunk])))
```

## Self-hosting

```bash
git clone https://github.com/snlagr/dns-llm
cd dns-llm
pip install -r requirements.txt

export CF_ACCOUNT_ID=your_account_id
export CF_API_TOKEN=your_api_token

python3 server.py       # port 5353
python3 server.py 53    # port 53 (requires root)
```

Deploy to a VPS:

```bash
./deploy.sh
```

---

[sonal.dev](https://sonal.dev) · dns-llm is a hobby project. Be kind to the resolver.
