# Lane policy icons

Lane keeps every policy icon used by generated profiles in this directory. The
published base URL is:

```text
https://raw.githubusercontent.com/wenjinliuu/Lane/main/assets/icons
```

All runtime icon paths are declared in `config/icons.yaml`; generated profiles
must not depend on an external icon repository. Lane does not draw, recolor or
badge policy icons. Every published PNG in this directory is copied unchanged
from the attributed upstream revision below.

## Qure assets

`third-party/qure/` contains an attributed subset copied unchanged from
[`Koolson/Qure`](https://github.com/Koolson/Qure) commit
`b16b260625f873266f6a6a9b88710132774997b8`.

Qure does not publish these files under a standard open-source license. Its
README requests attribution, restricts commercial use, and states that the
underlying marks remain the property of their respective owners. These files
are not covered by Lane's MIT license.

The mapping deliberately retains the pre-self-drawing appearance: AI uses
`AI.png`, Brokerage uses `Magic.png`, Crypto uses `Cryptocurrency_3.png`, and
each region's Auto and Manual groups share the same unchanged country/region
icon. The only selected replacements are Apple `Apple_1.png`, Streaming
`Netflix.png`, and Final `Global.png`. Taiwan continues to use `China.png` as
the previously settled icon choice.

Apple, Netflix, Microsoft, GitHub, Telegram, X, YouTube, TikTok, Emby, Steam,
Google and other names or marks belong to their respective owners. They are
used only to identify the corresponding user-selected routing group; Lane is
not affiliated with or endorsed by those owners.
