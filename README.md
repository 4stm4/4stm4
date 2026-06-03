# 4STM4

**Tiny infrastructure tools, embedded Linux experiments, and Rust-first network software.**

I build small, understandable systems for networking, homelab, embedded Linux, and automation.

**Write safe. Write fast. Write Rust.**

Website: https://4stm4.website

---

## Featured Projects

| Project | Focus |
| --- | --- |
| [nanodhcp](https://github.com/4stm4/nanodhcp) | Minimal DHCP server written in Rust. |
| [tinyWiFi](https://github.com/4stm4/tinyWiFi) | Minimal Wi-Fi router stack for Raspberry Pi Zero 2 W. |
| [Nervum](https://github.com/4stm4/nervum) | SDN and network-control experiments. |
| [Testum](https://github.com/4stm4/testum) | Homelab infrastructure platform experiments. |
| [pyjobkit](https://github.com/4stm4/pyjobkit) | Small Python automation/job toolkit. |
| [ehatrom / hatrom](https://github.com/4stm4/ehatrom) | Raspberry Pi HAT EEPROM tooling. |
| [Ocultum](https://github.com/4stm4/ocultum) | Embedded hardware and firmware experiments. |

---

## Focus

- Rust
- Embedded Linux
- Raspberry Pi
- Networking
- Homelab infrastructure
- Small understandable systems

---

## Current Direction

- minimal network services
- tiny router stack
- infrastructure automation
- embedded Linux tools
- Rust-first rewrites of existing tools

---

## Links

Website: https://4stm4.website  
GitHub: https://github.com/4stm4

---

## GitHub Traffic Collector

This repository includes a small GitHub REST traffic collector for selected 4STM4 repositories. It stores views, clones, referrers, and popular paths in `data/github_traffic.sqlite3`.

```sh
export GITHUB_TOKEN=github_pat_...
export GITHUB_OWNER=4stm4
python3 tools/github_traffic_collector.py
```

See [docs/github-traffic.md](docs/github-traffic.md) for token permissions, cron setup, and metric interpretation.

---

**Write safe. Write fast. Write Rust.**
