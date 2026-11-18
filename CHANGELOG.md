# Changelog

## [0.7.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.6.1...conductor-v0.7.0) (2026-11-18)


### Features

* **catalog:** read which models support reasoning ([08dd783](https://github.com/FedericoGrim/conductor/commit/08dd783843206c293f40bb5894a4a70d3944207d))
* **cli:** print the run progress after every step event ([f940249](https://github.com/FedericoGrim/conductor/commit/f94024912e497250ff0dce5361c48a99cd534bab))
* **cli:** print the run progress after every step event ([#60](https://github.com/FedericoGrim/conductor/issues/60)) ([0d01f0e](https://github.com/FedericoGrim/conductor/commit/0d01f0e5ec246dd8f5b43a67c35124d95d9517f6))
* **cli:** warn about parallel steps that list the same files ([#41](https://github.com/FedericoGrim/conductor/issues/41)) ([6eb98a7](https://github.com/FedericoGrim/conductor/commit/6eb98a7dc59938eb53a9a736ba9c6b586f76842e))
* **cli:** warn about parallel steps that share files ([cd91f76](https://github.com/FedericoGrim/conductor/commit/cd91f76516fec1e45b9b2b1cb04e5534c5c39790))
* **harness:** read the token usage of every harness's event stream ([5a71da9](https://github.com/FedericoGrim/conductor/commit/5a71da9228cadb16ff7489c16ed6a919abcf5057))
* **log:** sum the tokens per step and per model in run.json ([37d9688](https://github.com/FedericoGrim/conductor/commit/37d9688eafdf06fdaa84229057f37f3a67c7494b))
* **plan:** report parallel steps that list the same files ([8926aba](https://github.com/FedericoGrim/conductor/commit/8926ababc38cbfccef74cd605137e69ee601926a))
* **progress:** track step progress and estimate the time left ([22f7499](https://github.com/FedericoGrim/conductor/commit/22f7499986107e8502282240e4356096f97cb09c))
* **reviewer:** put the plan's domain rules before the specification ([8d514bc](https://github.com/FedericoGrim/conductor/commit/8d514bcf225d4384a19b0e60f2da3b2132a5a534))
* **reviewer:** put the plan's domain rules before the specification ([#92](https://github.com/FedericoGrim/conductor/issues/92)) ([c840fd4](https://github.com/FedericoGrim/conductor/commit/c840fd498ac25bda3ac0bc2ec8877cfedf97de13))
* **setup:** add a routing screen per model to the setup UI ([27fc475](https://github.com/FedericoGrim/conductor/commit/27fc475b16a4e4618884483708d722eba2329c22))
* **setup:** edit the routing options of a single model ([5709326](https://github.com/FedericoGrim/conductor/commit/5709326794f5caea317632596842e0c09dcd40aa))
* **setup:** edit the routing options of a single model ([#23](https://github.com/FedericoGrim/conductor/issues/23)) ([3ff58f8](https://github.com/FedericoGrim/conductor/commit/3ff58f8c3a928f5e92692254809a2dbf6547aa93))
* **stats:** show the tokens and the cache share per step and model ([86e5b5b](https://github.com/FedericoGrim/conductor/commit/86e5b5b263228b1e6c5fe909d3f2d043322e047f))
* **tokens:** record the tokens of every harness and show them in stats ([#91](https://github.com/FedericoGrim/conductor/issues/91)) ([363d704](https://github.com/FedericoGrim/conductor/commit/363d704685cb8ae9170fc7e454b3e172f4080abb))
* **tokens:** record worker and reviewer tokens per attempt ([0aabf17](https://github.com/FedericoGrim/conductor/commit/0aabf177e748055c3431e21e091f8beab033fe94))


### Bug Fixes

* **privacy:** declare reasoning for the Pi models the catalog marks ([65dba61](https://github.com/FedericoGrim/conductor/commit/65dba61a65bb2c3f6149a29eeadcfb9f21ce0ed6))
* **privacy:** declare reasoning for the Pi models the catalog marks ([#95](https://github.com/FedericoGrim/conductor/issues/95)) ([b1b3437](https://github.com/FedericoGrim/conductor/commit/b1b343742f9c4e1188eda6d7f5eda4bd09cb5206))


### Documentation

* describe the per-model routing screen of the setup UI ([2877d8c](https://github.com/FedericoGrim/conductor/commit/2877d8c58c16dbecb5a56254c24ac6c849fe8dc6))
* **integrations:** ask the brain to write plans in English ([ea8e2d1](https://github.com/FedericoGrim/conductor/commit/ea8e2d1c6038fd7d5834cd37eaaec95454e2b352))
* **integrations:** ask the brain to write plans in English ([#93](https://github.com/FedericoGrim/conductor/issues/93)) ([38f36b0](https://github.com/FedericoGrim/conductor/commit/38f36b0da505e97495a7865a4afc7b4cb296aa4f))
* list the progress module in the architecture ([f044f52](https://github.com/FedericoGrim/conductor/commit/f044f52b9c13f6353df8f2b2fab17c9ec3040c5e))

## [0.6.1](https://github.com/FedericoGrim/conductor/compare/conductor-v0.6.0...conductor-v0.6.1) (2026-11-16)


### Features

* **catalog:** read the cache prices and look a base URL's prices up once ([a5424b7](https://github.com/FedericoGrim/conductor/commit/a5424b7f839da54ba8caa6d203b69c6043ac554e))
* declare the model prices so a Pi step records a real cost ([3bf7815](https://github.com/FedericoGrim/conductor/commit/3bf7815e7cd8809446d68772b5299b8a5a74890a))
* **privacy:** declare each model's price in the Pi configuration ([98e42e1](https://github.com/FedericoGrim/conductor/commit/98e42e18b2915493e2e8c8b8c563ef6a75d7fad3))


### Bug Fixes

* a model unavailable in the region is a model error, and working free levels ([91068ac](https://github.com/FedericoGrim/conductor/commit/91068ac1c2184673cc37b67a9d3022350c46bb0d))
* **defaults:** replace the free models that are unavailable or unstable ([0e3874a](https://github.com/FedericoGrim/conductor/commit/0e3874ad255ac71fbfdd8fadfa5b9ad8641f3934))
* **errors:** treat a model unavailable in the region as unsuitable ([07f2213](https://github.com/FedericoGrim/conductor/commit/07f2213805cc6baf61cdf9797cc9a08eec6c3eb1))


### Documentation

* describe the region rule and record decision 025 ([5b99a72](https://github.com/FedericoGrim/conductor/commit/5b99a729daff183d22b01f51deae6c50a53ed171))
* drop the duplicated Refs 38 in decision 024 ([0cf90f8](https://github.com/FedericoGrim/conductor/commit/0cf90f8820846b8c6c4316912ba7665237dadc71))
* record the Pi prices and update decision 024 ([cd62d70](https://github.com/FedericoGrim/conductor/commit/cd62d70252734cd6f0c981e5722fb1ba6e67519f))


### Miscellaneous Chores

* release ([7d77e8a](https://github.com/FedericoGrim/conductor/commit/7d77e8ab62af4ae5eca26021d23bcf2f2bdf4b2c))

## [0.6.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.5.1...conductor-v0.6.0) (2026-11-14)


### Features

* a suspicious rejection gets a second opinion from the next reviewer ([a58c3b3](https://github.com/FedericoGrim/conductor/commit/a58c3b303287255941c6a944eae6de9cc70f072c))
* **brain:** read the brain's token usage from an OpenCode session ([c161f79](https://github.com/FedericoGrim/conductor/commit/c161f79ebc2f2278864f0a0237cae6270d63c2b3)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* **cli:** add the conductor stats command ([9e79f8c](https://github.com/FedericoGrim/conductor/commit/9e79f8ccc69d88541f5f417849d336feb12b6dc3)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* **commits:** choose an attempt's Conventional Commit message ([272c0bf](https://github.com/FedericoGrim/conductor/commit/272c0bf341864e6f690b33f74c3373d61a9b0cfe))
* **defaults:** add claude-haiku-5.5 as the second reviewer of medium ([c995c10](https://github.com/FedericoGrim/conductor/commit/c995c1000227e6ff07b0d444896ce855a0e626a7))
* **defaults:** choose the ladders on the measured benchmark ([e1e4361](https://github.com/FedericoGrim/conductor/commit/e1e4361317eef05affb9c1efcfa057f013f60b63))
* **escalation:** ask a second reviewer about a suspicious rejection ([bae9751](https://github.com/FedericoGrim/conductor/commit/bae9751937cc29a3f4168adccd8a983f95222dbe))
* **escalation:** give workers a working brief with the verify commands ([661645b](https://github.com/FedericoGrim/conductor/commit/661645ba0d3f247cb4a8dd62c34fc31bd4d6dc11))
* **harness:** run workers with Pi ([e156ca3](https://github.com/FedericoGrim/conductor/commit/e156ca3d42d411a642c89a813d9179d584171ab2))
* **log:** record the brain session and the subscription estimate in run.json ([e3de934](https://github.com/FedericoGrim/conductor/commit/e3de934e93df442551ff209f22dee76227360bd1)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* measure Conductor with conductor stats and a measurement protocol ([232b355](https://github.com/FedericoGrim/conductor/commit/232b355033820756e7160b62419301e62831e545))
* measure the models with a benchmark and choose the ladders on its numbers ([17af766](https://github.com/FedericoGrim/conductor/commit/17af766150c13916728b77dae9b855eeb42fe783))
* Pi as a third worker harness ([b888659](https://github.com/FedericoGrim/conductor/commit/b888659e942ed0a098c8b7f1efe5cd90281a1561))
* **privacy:** write a per-worktree Pi configuration ([0549d71](https://github.com/FedericoGrim/conductor/commit/0549d718e4ad7b3f1c40e5758c7097c05f2bfb89))
* reviewer verdicts name a category; passed checks settle theirs ([68dc556](https://github.com/FedericoGrim/conductor/commit/68dc556378b9b77b61102571ba1eafa65cbf0736))
* **reviewer:** commit attempts with the chosen message and review it ([c6d8bb3](https://github.com/FedericoGrim/conductor/commit/c6d8bb3077168007696130e8b519249ed7969a55))
* **reviewer:** name a category in every rejection and flag suspicious ones ([dda524b](https://github.com/FedericoGrim/conductor/commit/dda524b890acb8c323b0ebd16e18165066795985))
* **reviewer:** tell the reviewer what passed checks settle ([fe4be7d](https://github.com/FedericoGrim/conductor/commit/fe4be7d3f377d039eda0aaa7d1c49337ce3aa5e0))
* **scripts:** replay a recorded attempt to the reviewer ([4d4386b](https://github.com/FedericoGrim/conductor/commit/4d4386bab02e09926148526ed2a6758f5ae61365))
* **scripts:** report benchmark results per model ([56345ae](https://github.com/FedericoGrim/conductor/commit/56345ae6ddc178e46727b2714d7df8f7af09df3e))
* **scripts:** run benchmark tasks with Conductor and check them with hidden tests ([7479e09](https://github.com/FedericoGrim/conductor/commit/7479e09d0b9f830acb7ba23aa12b46b2c90e00e8))
* **stats:** build per-run and per-step statistics ([f6b5e33](https://github.com/FedericoGrim/conductor/commit/f6b5e339b1e685c8c7cb8125977c08e72a895583)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* **worker:** let a harness set environment variables for its worker ([cccbacf](https://github.com/FedericoGrim/conductor/commit/cccbacf19d9524c8488158f168d5d668d46a975d))
* working brief for workers and Conventional Commit messages they propose ([21a9158](https://github.com/FedericoGrim/conductor/commit/21a9158c73ace0ca0b580990c230e47de1f42128))


### Bug Fixes

* **benchmark:** check hidden tests in the right directory with a relative --out ([c234927](https://github.com/FedericoGrim/conductor/commit/c234927116916fae8b3ed0272684d8015bc173a3))
* **harness:** give Pi its key and read a stream error with exit code zero ([e55b44e](https://github.com/FedericoGrim/conductor/commit/e55b44e046269bf72b6b82548cf15d5e8a1ff2ea))
* isolate OpenCode workers from the user's skills and give them CLAUDE.md ([22c0292](https://github.com/FedericoGrim/conductor/commit/22c02922ca11046c9366d2a1aff44c7e6b124611))
* **privacy:** isolate OpenCode workers from the user's skills and give them CLAUDE.md ([c66e52b](https://github.com/FedericoGrim/conductor/commit/c66e52b196fed79b82172a1c74149e474fe06dc5)), closes [#61](https://github.com/FedericoGrim/conductor/issues/61)
* **rejections:** recognise ruff format by basename and as a formatter only ([0bf50b4](https://github.com/FedericoGrim/conductor/commit/0bf50b49ac76d42570de0b6889442acfeace131c))
* **stats:** skip a run.json that cannot be read or decoded ([26ec215](https://github.com/FedericoGrim/conductor/commit/26ec2159c0372bb2b59dfc572ffed41d91affc04)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)


### Documentation

* add the protocol and register for measuring Conductor ([e8b4086](https://github.com/FedericoGrim/conductor/commit/e8b40868dc0705100d22454c10dc04aa49f8deb0)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* **benchmarks:** say where the specs and the hidden tests come from ([86977f5](https://github.com/FedericoGrim/conductor/commit/86977f59df75c509aa8298fc71fd9d8d37c110f1))
* correct how a Pi worker gets its key and note its cost limit ([04e3e6c](https://github.com/FedericoGrim/conductor/commit/04e3e6cec03682273ece0e882a15bb2d8e0b0111))
* describe categorised verdicts and decision 021 ([41c150e](https://github.com/FedericoGrim/conductor/commit/41c150edee33c8e16a0c1972bfa7c0cce7352644))
* describe the isolation of OpenCode workers and decision 019 ([71cf128](https://github.com/FedericoGrim/conductor/commit/71cf128afc6dee8818b0804f3a9674ccd5954e9d)), closes [#61](https://github.com/FedericoGrim/conductor/issues/61)
* describe the model benchmark and how to rerun it ([00bd1b6](https://github.com/FedericoGrim/conductor/commit/00bd1b6bf15f8c838ddc7ad97d0ca1a82f42a6b3))
* describe the Pi harness and record decision 024 ([4db24cd](https://github.com/FedericoGrim/conductor/commit/4db24cd88375d3313e70c5844a2731c915c4c8b6))
* describe the second opinion and record decision 023 ([c0ddd0a](https://github.com/FedericoGrim/conductor/commit/c0ddd0a8b08c0196626029a30dd8b59aae6c8c97))
* document the working brief and worker commit messages ([cad81be](https://github.com/FedericoGrim/conductor/commit/cad81be741d22336a1453db60c8d67f002ec24c3))
* **escalation:** say that a suspicious rejection consults a second reviewer ([df93c81](https://github.com/FedericoGrim/conductor/commit/df93c8152ca99a70a81f735f55303e9fd1fd890f))
* point the Pi cost gap at issue 72 ([6c649cf](https://github.com/FedericoGrim/conductor/commit/6c649cfef48f60a7a4af69eb891b240e28fdfaf2))
* record the first measured task in the register ([d4e13ce](https://github.com/FedericoGrim/conductor/commit/d4e13ce12a3c8f6032258ad8348ab5a6a1ed864e)), closes [#37](https://github.com/FedericoGrim/conductor/issues/37)
* record the replay measurements in decision 021 ([b3e459f](https://github.com/FedericoGrim/conductor/commit/b3e459fb3322d90769009efe2a7888c3d7e0b358))

## [0.5.1](https://github.com/FedericoGrim/conductor/compare/conductor-v0.5.0...conductor-v0.5.1) (2026-11-13)


### Bug Fixes

* **escalation:** reject an attempt whose commit the git hooks refuse ([e24c682](https://github.com/FedericoGrim/conductor/commit/e24c68281f5ffac177d6a63cc889de8068bf5b24)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* **merge:** use a conventional merge message and report hook rejections ([869e003](https://github.com/FedericoGrim/conductor/commit/869e003cbdf3b6b623ae7f77af0851ebb778955e)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* run through the target repository's git hooks instead of crashing ([73ca1fe](https://github.com/FedericoGrim/conductor/commit/73ca1fe47c722d0cf98ca29d442c41603be5ec14))
* **scheduler:** fail a step that raises instead of stopping the run ([cf988fa](https://github.com/FedericoGrim/conductor/commit/cf988fa4cad7a9414d3543e0912a4e7b9ff3ce40)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* **worker:** commit with a conventional message and report hook rejections ([62a7f7e](https://github.com/FedericoGrim/conductor/commit/62a7f7efa18392c2697bd2c4797a551c4084865f)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)


### Documentation

* describe both worker harnesses in CLAUDE.md ([5f42f6c](https://github.com/FedericoGrim/conductor/commit/5f42f6c0f994afb4f7172ed14dcb6efd0531d104))
* describe both worker harnesses in CLAUDE.md ([d9979e9](https://github.com/FedericoGrim/conductor/commit/d9979e940da597fa38cd3d40b5c3c0255d0e4abf)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* describe how runs meet the target repository's git hooks ([228245b](https://github.com/FedericoGrim/conductor/commit/228245b06f5075ebea67f89b2852e851fd836cb4)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)

## [0.5.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.4.0...conductor-v0.5.0) (2026-11-12)


### Features

* classify model errors and end steps as unavailable instead of hanging ([b8bf431](https://github.com/FedericoGrim/conductor/commit/b8bf4316e431d34ab2762f250fafb01b44af255c))
* **cli:** run verification commands and send domain rules to the reviewer ([25d99ef](https://github.com/FedericoGrim/conductor/commit/25d99efb3e484493aa3a0b9739f775a1d243c857)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* **cli:** warn in validate when a level relies on a single provider ([f4694ae](https://github.com/FedericoGrim/conductor/commit/f4694ae087ade70e06469693d8b2bcbce2d1740b)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **config:** add a per-profile retry limit for transient errors ([b89c076](https://github.com/FedericoGrim/conductor/commit/b89c07659ee125d981668c71af1f79a23ed4377b)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **config:** allow an ordered list of models per level and for the reviewer ([dc24ece](https://github.com/FedericoGrim/conductor/commit/dc24eced78a496dd15b0ef1ab0f0a66d108b56a5)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **config:** name the harness of a provider and allow providers without an endpoint ([1739b3d](https://github.com/FedericoGrim/conductor/commit/1739b3da8d9e20fcd82f0d5bb194664ddb049c01)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* default fallbacks on a second provider, editable in setup ([1efcd46](https://github.com/FedericoGrim/conductor/commit/1efcd4612bfbbb295427bc4371f682f4f1cf03ee))
* **escalation:** end a step as unavailable on classified model errors ([b30a0f4](https://github.com/FedericoGrim/conductor/commit/b30a0f402f9e952aa8697e72342f23b59daa3b52)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **escalation:** fall back to the next model of a level on model errors ([2b7eceb](https://github.com/FedericoGrim/conductor/commit/2b7ecebc4bda75f51afb0a8a991064667d7fa53f)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **escalation:** stop a step on a worker question instead of guessing ([082448f](https://github.com/FedericoGrim/conductor/commit/082448f6787664a039fa5f426e59cb3c4e091bc1)), closes [#30](https://github.com/FedericoGrim/conductor/issues/30)
* **escalation:** verify an attempt before the review ([f1f6ce7](https://github.com/FedericoGrim/conductor/commit/f1f6ce7d67e693c96db423d91f6e511d5308fa29)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* fallback models within a level and for the reviewer ([e0a51fa](https://github.com/FedericoGrim/conductor/commit/e0a51fa6dd930f5350db67c576616ddb697ee76a))
* **harness:** run workers with Claude Code ([8146fd8](https://github.com/FedericoGrim/conductor/commit/8146fd82ce4195addba2cbfeb51dd61664d4aea6)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* **log:** count the cost of failed reviewers in the run totals ([de9922c](https://github.com/FedericoGrim/conductor/commit/de9922c951c5d82c829b68f5385d0ca4c2b2d6a0)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **log:** record the open question of a step in run.json ([ea528f9](https://github.com/FedericoGrim/conductor/commit/ea528f9e99b200286d319a784846707250f70d58)), closes [#30](https://github.com/FedericoGrim/conductor/issues/30)
* **plan:** declare domain rules and verification commands ([204f821](https://github.com/FedericoGrim/conductor/commit/204f821c4df06a8d855af855a22c9f1121759d8c)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* **plan:** let a step carry the answers to earlier questions ([1904a0d](https://github.com/FedericoGrim/conductor/commit/1904a0d1016d56b11e32293284199dae98dcb361)), closes [#30](https://github.com/FedericoGrim/conductor/issues/30)
* **privacy:** leave providers without an endpoint to their harness ([20c3d63](https://github.com/FedericoGrim/conductor/commit/20c3d63f92b7cf44390f3fe4e57eb8c11be8e2ee)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* **privacy:** unwrap Vercel gateway options for OpenCode ([d9efde8](https://github.com/FedericoGrim/conductor/commit/d9efde8f32c2adeae23747a4bc1328b77a346e3e)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **privacy:** write the fallback models into the worktree opencode.json ([97ff48c](https://github.com/FedericoGrim/conductor/commit/97ff48c2e9d8603f6e940c295b31f051c5a35303)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **reviewer:** hand the diff to the brain when the reviewer fails ([86c8aa1](https://github.com/FedericoGrim/conductor/commit/86c8aa14d3ade9412c434e6f8ac3caa92fba8c86)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **reviewer:** judge tests and domain rules with the verification results ([6b04efc](https://github.com/FedericoGrim/conductor/commit/6b04efc486c2740675865f4ec5f739f8fc6c0154)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* **reviewer:** try the reviewers in order and skip unusable providers ([eb2e2c8](https://github.com/FedericoGrim/conductor/commit/eb2e2c8b6010fc6dfc6dea85a8fae2fbb6bd1fc4)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* run workers with Claude Code as a harness chosen by the provider ([fee881e](https://github.com/FedericoGrim/conductor/commit/fee881edf6b19fa0d26aba039fa7d5469d7828b4))
* **setup:** add and remove fallback models for levels and the reviewer ([d1deb3f](https://github.com/FedericoGrim/conductor/commit/d1deb3fc74ec6c70a5915b7d447b3df9a7395abd)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **setup:** edit fallback models in the setup UI ([4d6d2e6](https://github.com/FedericoGrim/conductor/commit/4d6d2e63b3c432a62a9ac65084ba98f0aa42a9a7)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **setup:** keep the fallback models of every level and of the reviewer ([0fd3633](https://github.com/FedericoGrim/conductor/commit/0fd3633c364cc2a5cd685836b4bdb8590d68f9fc)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **setup:** offer Claude Code as a provider managed by its harness ([5f14779](https://github.com/FedericoGrim/conductor/commit/5f14779b3ada7f2698d75898eee8869c5adde06d)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* verify attempts with plan commands and review against tests and domain rules ([ad4069c](https://github.com/FedericoGrim/conductor/commit/ad4069c1520d653ab4e778fb13e78ed58028b3b7))
* **verify:** run a step's verification commands in its worktree ([d518516](https://github.com/FedericoGrim/conductor/commit/d518516afbba7ece2d4b70e01c53d55bab8023f0)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* **worker:** classify OpenCode provider errors ([b1581ce](https://github.com/FedericoGrim/conductor/commit/b1581ce1fd27955b5b9c667e44c514a08b6eb5c3)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* **worker:** keep the final text of an attempt ([ed3fdc0](https://github.com/FedericoGrim/conductor/commit/ed3fdc023f0cafafeee741df1e06b2ba9d484482)), closes [#30](https://github.com/FedericoGrim/conductor/issues/30)
* workers stop on open decisions with a question for the brain ([f167e65](https://github.com/FedericoGrim/conductor/commit/f167e6512161d481a4e4c837d5ed2d6d379efd4f))
* **worker:** stream OpenCode events and stop after the retry limit ([6811d70](https://github.com/FedericoGrim/conductor/commit/6811d705eab95c2c5491af1325e3c82c80e90adb)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)


### Bug Fixes

* **privacy:** keep the data policy on models OpenCode picks itself ([fadb411](https://github.com/FedericoGrim/conductor/commit/fadb411f13a047624e887d2e272dd05f91d6a7cb))
* **privacy:** keep the profile's data policy on models OpenCode picks itself ([eb333b6](https://github.com/FedericoGrim/conductor/commit/eb333b6fcf6084ac184447329b91890e29fb5c77))
* **reviewer:** never send the API key to a base URL that is not https ([6c8a7f6](https://github.com/FedericoGrim/conductor/commit/6c8a7f63b0aa0119cf047981f82e974eeba4983e))
* **reviewer:** never send the API key to a base URL that is not https ([7cb879e](https://github.com/FedericoGrim/conductor/commit/7cb879ec7df0c6984b18112274f916533dd10950))


### Documentation

* **decisions:** accept 011 with verified OpenCode error classes ([66da435](https://github.com/FedericoGrim/conductor/commit/66da435baea224d8e3fc3a6637c1b3df21828665))
* **decisions:** propose fallback models, autonomy levels and step agents ([b5fac3d](https://github.com/FedericoGrim/conductor/commit/b5fac3d8e1883faf56de95a94478afdc36fa5403))
* **decisions:** propose fallback models, autonomy levels and step agents ([f1c3c89](https://github.com/FedericoGrim/conductor/commit/f1c3c898534d73731c5d1fc06b6c5f618801d4e8))
* describe fallback models for levels and reviewers ([a2fba43](https://github.com/FedericoGrim/conductor/commit/a2fba4339d0e1be7beb6deaf9abbe597b92642b8)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* describe provider harnesses and endpoint-less providers ([e32859e](https://github.com/FedericoGrim/conductor/commit/e32859e15b280177e5600a1bc45ef3ba6d113700)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* describe the Claude Code harness and decision 017 ([a672ad5](https://github.com/FedericoGrim/conductor/commit/a672ad50abb057543327f19af497efe9858b5dd7)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* describe the default fallbacks and decision 014 ([8af5955](https://github.com/FedericoGrim/conductor/commit/8af59558e30fb3e551c71d275e96d0315161f47f)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* describe the harness module ([658e77e](https://github.com/FedericoGrim/conductor/commit/658e77e6487fb533cde2900080f44ec4890ee2f3)), closes [#31](https://github.com/FedericoGrim/conductor/issues/31)
* describe the unavailable state and reviewer errors ([946314a](https://github.com/FedericoGrim/conductor/commit/946314ae324764f99947482fcb7a7adf1779867d)), closes [#34](https://github.com/FedericoGrim/conductor/issues/34)
* describe verification commands, domain rules and decision 016 ([0eee061](https://github.com/FedericoGrim/conductor/commit/0eee0614822b7c84e2be25e5b77caa55015c7de5)), closes [#32](https://github.com/FedericoGrim/conductor/issues/32)
* describe worker questions, needs_answer and decision 015 ([ec9c8fa](https://github.com/FedericoGrim/conductor/commit/ec9c8fa6aa6b81abd4affb98e459016336fdb337)), closes [#30](https://github.com/FedericoGrim/conductor/issues/30)
* explain how the data policy reaches OpenCode's own requests ([ec22ce7](https://github.com/FedericoGrim/conductor/commit/ec22ce7fa05233889d67b0a673910d45193304b9))
* note that a model reviewer needs an https base URL ([46f516a](https://github.com/FedericoGrim/conductor/commit/46f516af892a045657fa38484983fcd217361350))

## [0.4.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.3.1...conductor-v0.4.0) (2026-11-11)


### Features

* **cli:** add config path, export and import commands ([cbbeabe](https://github.com/FedericoGrim/conductor/commit/cbbeabe9d7fea9184e7fa1b886738644c9cef447))
* **config:** allow request options per model for gateway routing ([f274f5a](https://github.com/FedericoGrim/conductor/commit/f274f5a4051b6eb458b30423b3943ae93fb3cdbe))
* export and import the settings of an instance ([c04c95e](https://github.com/FedericoGrim/conductor/commit/c04c95e284d81665ae45bc77e42c69b21fdfbda9))
* request options per model for gateway upstream routing ([673aadf](https://github.com/FedericoGrim/conductor/commit/673aadfeaccb02d0b20b124ae19a11eed66a98e3))
* **settings:** export and import the settings of an instance ([45d274a](https://github.com/FedericoGrim/conductor/commit/45d274a4c323e291c14f95be93c637c69c03be28))


### Documentation

* describe settings export and import, decision 010 ([c26840a](https://github.com/FedericoGrim/conductor/commit/c26840a7745450c19796372015b84c75c73c01bc))

## [0.3.1](https://github.com/FedericoGrim/conductor/compare/conductor-v0.3.0...conductor-v0.3.1) (2026-11-11)


### Documentation

* **integrations:** make the conductor skill declare itself for multi-step work ([61e66d6](https://github.com/FedericoGrim/conductor/commit/61e66d6ba8e2daad87ffea36325caee09c400321))
* **integrations:** make the conductor skill declare itself for multi-step work ([48efbf2](https://github.com/FedericoGrim/conductor/commit/48efbf2b5fb5643cc22f42b1ee308c9f184c64ab))

## [0.3.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.2.0...conductor-v0.3.0) (2026-11-11)


### Features

* billing commands, per-run cost and cross-project spend ledger ([c061ad9](https://github.com/FedericoGrim/conductor/commit/c061ad90289a521796db94fac310100833ede7c0))
* **billing:** keep a spend ledger across projects and total it ([d2ce352](https://github.com/FedericoGrim/conductor/commit/d2ce35225cbfd201d68cec7b4f7e4519c5335b1f))
* **billing:** read balances from OpenRouter, Vercel AI Gateway and Scaleway ([c0b44cf](https://github.com/FedericoGrim/conductor/commit/c0b44cf6325414575a7bb1a4f0c080bfef0ba9ab))
* **billing:** refuse plain http, accept string amounts, survive a read-only ledger ([adfbd3d](https://github.com/FedericoGrim/conductor/commit/adfbd3d2fb225161834157bdc5ac965619941a73))
* **billing:** report unreachable providers and unexpected responses ([304f3dc](https://github.com/FedericoGrim/conductor/commit/304f3dcd57634dd3112e3878feceeea7a7c67b4b))
* **catalog:** hide batch-only variants that OpenCode cannot run ([7954e4b](https://github.com/FedericoGrim/conductor/commit/7954e4b1ca39641d0ee67eb2c49c36566ff38f11))
* **catalog:** read OpenRouter and Vercel model lists and filter them ([11e75c3](https://github.com/FedericoGrim/conductor/commit/11e75c33b62da062f1039bf09f7e5c3a7171c86d))
* **cli:** add billing commands and record every run in the ledger ([cad210b](https://github.com/FedericoGrim/conductor/commit/cad210b0b5423c5b628397ad4cc5dbca2a6733f6))
* **cli:** add the interactive conductor setup command ([2154e35](https://github.com/FedericoGrim/conductor/commit/2154e35ad4a0fbfed23a012ec648628c5ae45d91))
* **cli:** report billing project outside a git repository as an error ([a81cfed](https://github.com/FedericoGrim/conductor/commit/a81cfed6bf6900d51931affeabc01178e24ce685))
* **config:** write conductor.toml from a Config ([cbc9760](https://github.com/FedericoGrim/conductor/commit/cbc976071c0d78d65c9dd6668638acd8b9cfb5d0))
* **credentials:** read reviewer and billing keys from the stored file ([b068997](https://github.com/FedericoGrim/conductor/commit/b06899714d641a9d427c291ed579f4f6259a7e4e))
* **credentials:** store API keys in an owner-only file, environment first ([c090114](https://github.com/FedericoGrim/conductor/commit/c090114c8cb053603b170677f5cfdeda540ff3a0))
* **escalation:** record worker and reviewer cost for every attempt ([92331b0](https://github.com/FedericoGrim/conductor/commit/92331b08b91cc66e41697318eada838199bc57cf))
* interactive setup TUI for profiles, tiers and API keys ([375bf5e](https://github.com/FedericoGrim/conductor/commit/375bf5e3c618d58b0cb277d975dbd193bb655763))
* **log:** total the cost per step, per model and per run in run.json ([4262802](https://github.com/FedericoGrim/conductor/commit/4262802e4e4b4912ac6f79cadb275289ab9828b2))
* multi-provider profiles with five fixed difficulty levels ([be8caf2](https://github.com/FedericoGrim/conductor/commit/be8caf25470632494f043d3840033018bbf7b347))
* profiles with several providers and five fixed difficulty levels ([fdde3cb](https://github.com/FedericoGrim/conductor/commit/fdde3cb907371bc996398958c37b752d76038d4d))
* **setup:** model profiles, tiers and validation for the setup TUI ([ead5679](https://github.com/FedericoGrim/conductor/commit/ead5679c8c68e427e70ffc9da9bcd4843e758e4d))
* **setup:** prefix model ids with the provider and allow typing an id by hand ([f856c1f](https://github.com/FedericoGrim/conductor/commit/f856c1fe65f0b8773b01b88a559f921c8ee641d8))
* **setup:** screens, keys and rendering for the setup TUI ([7b8efa3](https://github.com/FedericoGrim/conductor/commit/7b8efa3237340fc432cbc54f5fdcf62987aae33b))
* **worker:** read the cost of an attempt from OpenCode events ([5d479d4](https://github.com/FedericoGrim/conductor/commit/5d479d45d26c51310791282e8d944706ce7034ab))


### Documentation

* describe multi-provider profiles, five difficulty levels and the defaults ([842c9ba](https://github.com/FedericoGrim/conductor/commit/842c9ba240a8639adb2fee7bf92ad9201ade81de))
* describe the billing commands, the spend ledger and decision 004 ([4f256d7](https://github.com/FedericoGrim/conductor/commit/4f256d7b538bf1dad18f2fa16455dca7d717cec8))
* document the release-please token and its manual fallback ([e401046](https://github.com/FedericoGrim/conductor/commit/e40104625c9668d0eddade2429e0bfc80cfe6ba5))

## [0.2.0](https://github.com/FedericoGrim/conductor/compare/conductor-v0.1.0...conductor-v0.2.0) (2026-11-11)


### Features

* **cli:** add run and validate commands wiring the whole pipeline ([9f82e2a](https://github.com/FedericoGrim/conductor/commit/9f82e2a03180cb9f4bd27479199b144925f9a3ec))
* **config:** load privacy profiles from conductor.toml ([ab4a47c](https://github.com/FedericoGrim/conductor/commit/ab4a47c5f17bf1be3ed166588f99dd0176f0ff78))
* core pipeline (plan, scheduler, worker, reviewer, escalation, log, merge, CLI) ([1c53cad](https://github.com/FedericoGrim/conductor/commit/1c53cadf5c62ee64e94b936547cdaf7948a61805))
* **escalation:** escalate rejected steps to the next tier with feedback ([c32603a](https://github.com/FedericoGrim/conductor/commit/c32603a300029360867fd9ea946d6a51a91a226a))
* **log:** write run.json and attempt files under .conductor/runs ([e44a950](https://github.com/FedericoGrim/conductor/commit/e44a950ec153efbbbc64aa1d59858d92070da909))
* **merge:** merge approved branches and report conflicts ([247141f](https://github.com/FedericoGrim/conductor/commit/247141f0cc817ddc193911c19082519d04ae1092))
* **plan:** parse and validate plan.json with dependency ordering ([5cbfe9b](https://github.com/FedericoGrim/conductor/commit/5cbfe9b8e7aa06f65eadcfdc8fbed785e009e20e))
* **privacy:** build opencode.json routing config from a profile ([b7a45f8](https://github.com/FedericoGrim/conductor/commit/b7a45f884a2c5acc6da279b8109498b4ecf6df13))
* **reviewer:** call OpenAI-compatible endpoint and parse strict verdict ([f3ba999](https://github.com/FedericoGrim/conductor/commit/f3ba99970510f495156df109d10a63134c1e9fb3))
* **scheduler:** run ready steps concurrently, skip dependents of failures ([53b480c](https://github.com/FedericoGrim/conductor/commit/53b480c0bc2be99ad0552185099501ccab6af300))
* **worker:** run opencode in a worktree and capture events and diff ([89dce0b](https://github.com/FedericoGrim/conductor/commit/89dce0bb1fabe53e2234f97fdf6b0380c44d4b9c))


### Bug Fixes

* **scripts:** list-models works on the EU endpoint; verified model ids ([78305b3](https://github.com/FedericoGrim/conductor/commit/78305b31c622b5083c203dd5854a7759970bc146))
* **scripts:** send a User-Agent and skip router pseudo-models in list-models ([709b429](https://github.com/FedericoGrim/conductor/commit/709b42924f556aead2cfe24525bde5c7efaa4d93))
* **worker:** set PWD for opencode and exclude .conductor/ from git ([672137e](https://github.com/FedericoGrim/conductor/commit/672137eae0b7a5614d368a0ebda9556f99a856bf))
* **worker:** set PWD for opencode and exclude .conductor/ from git ([ac2ab73](https://github.com/FedericoGrim/conductor/commit/ac2ab73cc01b25afcacb68b91d189f7f3addc4bd))


### Documentation

* add Claude Code skill and OpenCode command for the brain ([1cd2780](https://github.com/FedericoGrim/conductor/commit/1cd2780a588552e2fed71671d48dd00b30a899b5))
* add conductor.toml.example with three privacy profiles ([69bbec2](https://github.com/FedericoGrim/conductor/commit/69bbec2bf5819651d5dc7074bdbef1589691ce8c))
* add example plan.json ([738890a](https://github.com/FedericoGrim/conductor/commit/738890aad0513031a3fb5c2b483703daac3b4210))
* add project CLAUDE.md and decision log ([8697eba](https://github.com/FedericoGrim/conductor/commit/8697eba6062f63b43083d63bd6b5316911035957))
* describe the run flow, privacy levels, install and plan format ([fd7c056](https://github.com/FedericoGrim/conductor/commit/fd7c056dcdc9b037c15f2c2f0621181eb5e19189))
* use verified OpenRouter model ids in conductor.toml.example ([19c9827](https://github.com/FedericoGrim/conductor/commit/19c98273166b08bb1da7ac4b15ce5837c21d212d))
