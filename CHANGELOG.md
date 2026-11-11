# Changelog

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
