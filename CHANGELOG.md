## v0.4.0 (2026-03-30)

### Feat

- **api**: add versions param to init_api() ([e80ca06](https://github.com/aignostics/foundry-python-core/commit/e80ca06c77a7fb77604a728103d535dfca47c4ec))
- **foundry**: add python_version to FoundryContext ([0878ae7](https://github.com/aignostics/foundry-python-core/commit/0878ae7713502f4565ddde769413d9a49ab923a9))

### Fix

- **sentry**: derive env_prefix from FoundryContext ([4c4b748](https://github.com/aignostics/foundry-python-core/commit/4c4b748f154c9f4fc9f345861122e28649e99626))

## v0.3.0 (2026-03-30)

### Feat

- use FoundryContext in all modules (#18) ([a99873c](https://github.com/aignostics/foundry-python-core/commit/a99873c99ff0c7bd68e9f8f9dd5301766709a731))
- **di**: drop project_name, use context only ([4959a59](https://github.com/aignostics/foundry-python-core/commit/4959a59510af03b000cf6cde7dae14e0111a1e56))
- **foundry**: add FoundryContext and set_context() ([3cf6f69](https://github.com/aignostics/foundry-python-core/commit/3cf6f6959654f9f0e76bcef5a0707cff0a7e6cc0))
- **gui**: add NiceGUI page helpers and nav builder ([49e28f6](https://github.com/aignostics/foundry-python-core/commit/49e28f6f3f5ae6c6a1fbdcb7a4260af5c4e97990))
- **boot**: add parameterised boot() sequence ([cb63a75](https://github.com/aignostics/foundry-python-core/commit/cb63a75824aa9f9fccba76a165113f22af563893))
- **api**: add VersionedAPIRouter, init_api, and api package ([b003c21](https://github.com/aignostics/foundry-python-core/commit/b003c2118ca88805218656a738c97207b7210a14))
- **api**: add Auth0 authentication dependencies ([47dbd6f](https://github.com/aignostics/foundry-python-core/commit/47dbd6fbcac06f911cbdab51e335202ced8f1195))

### Fix

- **tests**: extract constants, document empty stubs ([784af4f](https://github.com/aignostics/foundry-python-core/commit/784af4f9df2a0dc9ed6e0056c8c144ff2b053e26))
- **gui**: render page content inside frame context ([e524978](https://github.com/aignostics/foundry-python-core/commit/e524978384dc396fbbe7c193331616bcca697fe6))

### Refactor

- **gui**: extract helpers to reduce gui_run complexity ([5beeaf3](https://github.com/aignostics/foundry-python-core/commit/5beeaf3e424eb7396a7a4edd7addfb3a05d79e21))

## v0.2.0 (2026-03-26)

### Feat

- **cli**: add prepare_cli with project_name injection ([78cc4e1](https://github.com/aignostics/foundry-python-core/commit/78cc4e16394d4522707f7d3f018d13cb1427719b))
- **database**: add async SQLAlchemy session management ([af91937](https://github.com/aignostics/foundry-python-core/commit/af91937c9fa838f1eb297449662beb6e744c1e83))
- **service**: add BaseService with FastAPI DI support ([c393d9a](https://github.com/aignostics/foundry-python-core/commit/c393d9af562dbb9ce0a7cbc63bdcf7f7a95c1f74))
- **user_agent**: add parameterised user_agent() ([ae3b27b](https://github.com/aignostics/foundry-python-core/commit/ae3b27b2270579310cf38e0b2fb92dfe3687708d))
- **sentry**: add configurable sentry_initialize and SentrySettings ([61fd5c8](https://github.com/aignostics/foundry-python-core/commit/61fd5c824f7f387ae090c325434771c9ff56a32a))
- **log**: add configurable logging_initialize and LogSettings ([e283f67](https://github.com/aignostics/foundry-python-core/commit/e283f67d86577dbd42094230c7d11714d67517c7))
- **api**: add ApiException hierarchy and handlers ([b055518](https://github.com/aignostics/foundry-python-core/commit/b055518d812687c43a5e3e6366614d6aa36a320f))
- **process**: add ProcessInfo and get_process_info ([c8d168f](https://github.com/aignostics/foundry-python-core/commit/c8d168fab874d98cdd6022bb0554090c92a1c3ac))
- **models**: add OutputFormat StrEnum ([e19cea5](https://github.com/aignostics/foundry-python-core/commit/e19cea57017502cdb4c48217a5eefa8e2d1497a8))

## v0.1.0 (2026-03-26)

### Feat

- **di**: add dependency injection module ([e351ea8](https://github.com/aignostics/foundry-python-core/commit/e351ea85cee6e723d7001b5c18e3f886ccf566af))
- **settings**: add OpaqueSettings and load_settings (#7) ([fc25de4](https://github.com/aignostics/foundry-python-core/commit/fc25de49cc9dc64a3a2b3736be9396085002b092))
- **console**: add themed Rich console (#6) ([337efb6](https://github.com/aignostics/foundry-python-core/commit/337efb649b9b324989a1dc2c1f8d13ef24b843b7))
- add health module ([2b656bb](https://github.com/aignostics/foundry-python-core/commit/2b656bb5dfe03275aa1d942c5cab16d14077d50e))
