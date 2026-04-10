## v0.11.0 (2026-04-10)

### Feat

- **scheduler**: add BaseJoblet to foundry-core ([a707e8c](https://github.com/aignostics/foundry-python-core/commit/a707e8c8e0f11b0456625cafe291a4adac46efcf))

## v0.10.0 (2026-04-10)

### Feat

- **gui**: default page title to context name ([928c4da](https://github.com/aignostics/foundry-python-core/commit/928c4dad7bced7513457c0b78837bb1364555b2f))

### Refactor

- **gui**: extract _frame_context to reduce cognitive complexity ([a4134d9](https://github.com/aignostics/foundry-python-core/commit/a4134d90e76f921d82a16f2245ec771ec76ad64f))
- clean duplicate test helpers/fixtures ([3fa8882](https://github.com/aignostics/foundry-python-core/commit/3fa88827196d06eb6ae78209d85b8b33e88ec14f))

## v0.9.0 (2026-04-09)

### Feat

- **gui**: registry-based page registration with frame injection (#39) ([c22b79e](https://github.com/aignostics/foundry-python-core/commit/c22b79e02c1a920a127400a045ead2db5e181fe4))

## v0.8.2 (2026-04-08)

### Fix

- trigger version bump ([994f9f5](https://github.com/aignostics/foundry-python-core/commit/994f9f5e1898eac1b6c3c95d5b933d895e4ceea0))

## v0.8.1 (2026-04-08)

### Fix

- **api**: propagate exception handlers to versioned apps ([47a78a0](https://github.com/aignostics/foundry-python-core/commit/47a78a0356615eb56a8bd95745c9de0047bb8798))

## v0.8.0 (2026-04-07)

### Feat

- **foundry**: add PackageMetadata to FoundryContext ([8e8f904](https://github.com/aignostics/foundry-python-core/commit/8e8f90429999e485d49f1feddf903ee0eba80b1f))

### Refactor

- **api**: derive metadata from context in api.core helpers ([df0a01f](https://github.com/aignostics/foundry-python-core/commit/df0a01fb582dc9163af081a32fb6233d9646c2e9))

## v0.7.2 (2026-04-02)

### Fix

- **api**: guard get_user against non-dict session ([6828e28](https://github.com/aignostics/foundry-python-core/commit/6828e28b36026e25e6f75948c1589c156b59f6cb))

## v0.7.1 (2026-04-02)

### Fix

- **database**: normalise asyncpg to psycopg in get_url ([4918893](https://github.com/aignostics/foundry-python-core/commit/4918893a261ec69e4a60daa991dc71166212f9c9))

## v0.7.0 (2026-04-01)

### Feat

- **database**: resolve env_file from active context in DatabaseSettings ([1bb1483](https://github.com/aignostics/foundry-python-core/commit/1bb1483b86e743b06ddadda1af1af47d7480ccc3))

### Fix

- **foundry**: detect db url in .env files in from_package ([e6bd18d](https://github.com/aignostics/foundry-python-core/commit/e6bd18d3d11d1c509f7eaf61255cdeb27c232505))

## v0.6.2 (2026-03-31)

### Fix

- **database**: env var for db_name is NAME not DB_NAME ([e1418ab](https://github.com/aignostics/foundry-python-core/commit/e1418ab27ca1ac154d6a61f9142ad6e346c4f1e8))

## v0.6.1 (2026-03-31)

### Fix

- **database**: rename max_overflow to pool_max_overflow ([5c7f26c](https://github.com/aignostics/foundry-python-core/commit/5c7f26ca1cce0a254d39e4547530397f2ffc6493))

## v0.6.0 (2026-03-31)

### Feat

- add autoconfigured DatabaseSettings ([0de7adf](https://github.com/aignostics/foundry-python-core/commit/0de7adf41f5c8138c3428424f07a839a6b46b0d8))
- **foundry**: auto-inject third_party into sys.path ([884b120](https://github.com/aignostics/foundry-python-core/commit/884b12096e82b2591a4ed1d70bb3149b3d393154))

### Fix

- **api**: make AuthSettings fields mandatory ([acf40ec](https://github.com/aignostics/foundry-python-core/commit/acf40ec3111b17573439f627fcfc2e4c58f4dde4))

## v0.5.0 (2026-03-31)

### Feat

- **foundry**: add version_with_vcs_ref to FoundryContext ([424a1e4](https://github.com/aignostics/foundry-python-core/commit/424a1e4dfcccc157b208f03238b14c8d72e5918c))

### Refactor

- **user_agent**: replace explicit params with context ([d903eb2](https://github.com/aignostics/foundry-python-core/commit/d903eb22441858fabe4488809937aba89858124c))
- **tests**: replace direct FoundryContext() calls with make_context() helper ([a44d9ad](https://github.com/aignostics/foundry-python-core/commit/a44d9adea4ba7a57dd278a62cfa7d43e60177217))

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
