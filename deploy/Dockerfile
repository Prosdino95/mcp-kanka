# =============================================================
#  Kanka MCP server over Streamable HTTP
#  Built from the selfhosted branches of the two forks.
# =============================================================
FROM python:3.14.7-slim

# Commits to build, passed by docker-compose.yml. A SHA rather than a
# branch name: with a branch the line below never changes, Docker reuses
# the cached layer and the image silently keeps old code.
ARG PYTHON_KANKA_REF
ARG MCP_KANKA_REF

# python-kanka first, from the fork. mcp-kanka pins python-kanka==2.6.2,
# which the fork also reports, so pip keeps it instead of fetching the
# upstream release from PyPI, which ignores KANKA_BASE_URL.
RUN pip install --no-cache-dir \
        "python-kanka @ https://github.com/Prosdino95/python-kanka/archive/${PYTHON_KANKA_REF}.tar.gz" \
 && pip install --no-cache-dir \
        "mcp-kanka @ https://github.com/Prosdino95/mcp-kanka/archive/${MCP_KANKA_REF}.tar.gz"

# Fail the build, not the first request, if pip swapped in upstream code
RUN python -c "import inspect, kanka.client as c; assert 'KANKA_HOST_HEADER' in inspect.getsource(c), 'python-kanka is not the fork'" \
 && python -c "from mcp_kanka.__main__ import build_http_app"

RUN useradd --create-home --uid 1000 mcp
USER mcp

ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["python", "-m", "mcp_kanka"]
