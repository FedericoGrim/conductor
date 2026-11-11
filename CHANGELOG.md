# Changelog

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
