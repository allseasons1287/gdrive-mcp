# Allowlist Reference

Folder IDs in `allowlist.json` map to these Drive folders.

| Folder ID | Path | Notes |
|---|---|---|
| `1o-XuiXQw1PUvyh3PUFylULWQjyc4uyNq` | `My Drive/CLAUDE - PERSONAL/PERSONAL HEALTH AND FITNESS` | Master health folder. Descendants inherit access. |

## NOT in allowlist (intentionally blocked)

- `My Drive` root (`0AKjpjXO-vOWLUk9PVA`)
- `VAL` folder (`12W07Fykkv2dxZJEUcQMWm52h2KxkIoa6`)
- `RANDOM MUESUEM DAY` (`1QItI7s0Het0DDztp5Lw6Abm_bV7X4HIo`)
- `CLAUDE - PERSONAL` directly (`1tkWCIpPEo022N4bD9biKMPadkwH-dUu8`)

## To add a new folder

1. Get the folder ID
2. Add to `allowed_folder_ids` array
3. Document mapping
4. Commit + push (Railway auto-redeploys)
5. Share folder with service account at Editor permission
