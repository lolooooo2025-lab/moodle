# Bundled Linux runtime provenance

The archive `python-runtime.tar.gz` is a relocatable Linux x86-64 runtime built
for the Netlify Node adapter. It is not a Netlify-supported Python runtime; it is
an application-bundled executable launched by the JavaScript function.

| Component | Version | Source | License |
|---|---:|---|---|
| CPython | 3.11.14 | `python/cpython` tag `v3.11.14`, commit `b37291ec09b4b75a451735d6d356e4c2e27c7e69` | PSF, `LICENSE.CPython` in archive |
| OpenSSL | 3.5.4 | `openssl/openssl` tag `openssl-3.5.4` | Apache-2.0, `LICENSE.OpenSSL` in archive |
| libffi | 3.4.8 headers / Debian runtime `libffi.so.8.1.2` | `libffi/libffi` tag `v3.4.8`; Debian 12 runtime library | MIT, `LICENSE.libffi` in archive |
| zlib | 1.3.1 | `madler/zlib` tag `v1.3.1` | zlib, `LICENSE.zlib` in archive |
| PostgreSQL client (`pg_dump`, `libpq`) | 18.6 | `postgres/postgres` tag `REL_18_6`, commit `724edf9bde9d356724ad384a2e196edc3c9f80f7` | PostgreSQL, `LICENSE.PostgreSQL` in archive |

Build notes:

- CPython was compiled with `--enable-shared --with-openssl=<prefix>` and a
  relocatable `$ORIGIN/../lib` runpath. The adapter also sets `LD_LIBRARY_PATH`.
- OpenSSL and zlib were linked statically into the Python extensions.
- `pg_dump` was built from the PostgreSQL 18.6 client sources. Only `pg_dump`
  and `libpq` are shipped; no PostgreSQL server is bundled or started.
- The archive SHA-256 is pinned in `netlify/build.mjs`.
- Python package versions remain pinned by the original `requirements.lock.txt`.

SHA-256 (`python-runtime.tar.gz`):

```text
659c2d81a91a346bcba9ad9b44377aa1c6e47cc9f8cfdbffc70a70a1963797e6
```
