# Product-page check

Only with a real browser tool (e.g. Claude in Chrome), and only for the final
shortlist (max 5 products). Galaxus pages answer plain HTTP fetches with 403,
so without a real browser every field is *blocked*.

Per product page (`pageUrl`), read the page **text** (not screenshots) and
extract:

| Field | What to look for |
|---|---|
| availability | the stock/availability text near the price |
| delivery | the delivery estimate ("delivered between …") |
| seller | Galaxus itself or a marketplace seller |
| price | current page price vs the search price; flag any difference |

Label each field *checked*, *not checked* or *blocked*:

- *checked*: read from the page text.
- *not checked*: the page loaded but the field was not visible.
- *blocked*: 403, a page that needs JavaScript you cannot run, or bot
  protection. Stop at a captcha; never solve one.

Expect 5–15 s and a few thousand tokens per page.
