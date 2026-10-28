FROM python:3.12-slim AS builder
WORKDIR /build
COPY . .
# A source snapshot has no Git metadata; this is an example image, not a release.
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_YAMCPS=0.0.0+oauth.example
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels . ./plugins/yamcps-demo

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 yamcps
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/yamcps-*.whl \
    && pip install --no-cache-dir --no-deps /wheels/yamcps_demo-*.whl \
    && rm -rf /wheels
USER yamcps
WORKDIR /home/yamcps
ENTRYPOINT ["yamcps"]
