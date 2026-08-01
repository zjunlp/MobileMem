# Media Asset Inventory

The project page bundles images, video, research figures, and dataset excerpts under `assets/web/`.

## Asset groups

| Paths                                              | Content                                  |
| -------------------------------------------------- | ---------------------------------------- |
| `assets/web/institutions*.png`                     | OPPO and OpenKG.CN identity marks        |
| `assets/web/paper/`                                | Figures from the MobileMem paper         |
| `assets/web/case-*.jpg`, `assets/web/xiaobu-*.png` | Interactive MobileMem case demonstration |
| `assets/web/memweb/**/*.png`                       | Curated MobileMem application samples    |
| `assets/web/memweb/trajectories*.js`               | User–AI dialogue samples                 |
| `assets/web/videos/oppo-application-scenarios.mp4` | OPPO application-scenario video          |

## Image manifest

`assets/web/memweb/image-manifest.json` records paths, dimensions, byte sizes, display labels, and
SHA-256 checksums for the 360 displayed dataset images. Run `npm run images:check` to verify it.
