# Sourced by scripts/dev.sh (T31): providers are fake unless the person explicitly asks for
# real ones. Fake mode (POST3_FAKE_PROVIDERS=1) makes placeholder media and spends nothing;
# `POST3_REAL=1 make dev` is the only way a dev server ever calls a paid provider, and the
# web shell then shows a persistent "REAL: spends credits" badge (GET /api/doctor).
if [[ "${POST3_REAL:-}" == "1" ]]; then
  unset POST3_FAKE_PROVIDERS
  POST3_PROVIDERS=real
else
  export POST3_FAKE_PROVIDERS=1
  POST3_PROVIDERS=fake
fi
