FROM ollama/ollama:latest

ARG LLM_MODEL=gemma3:1b
ENV OLLAMA_HOST=0.0.0.0
ENV LLM_MODEL=${LLM_MODEL}


RUN /bin/sh -c "ollama serve >/tmp/ollama-build.log 2>&1 & sleep 10 && ollama pull ${LLM_MODEL} && pkill ollama || true"

CMD ["ollama", "serve"]
