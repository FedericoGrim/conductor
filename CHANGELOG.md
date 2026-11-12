# Changelog

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
