# Add a creator or scenery package

1. Open the original creator/listing page. Verify that the item is freeware and
   within scope. Do not download or redistribute the scenery to populate metadata.
2. Copy a package structure from an existing JSON catalogue. Assign a stable ID;
   use the numeric Flightsim.to ID to avoid collisions when names change.
3. Record the creator username, exact original URL and supported facts. Attribute
   every verified field using `verification.sources`. Date the check. Describe
   an inference explicitly; keep unsupported values `unknown`.
4. Independently verify licences and dependencies before recording them as known.
   A listing marked free does not make its assets open source. Never treat a
   simulator label as a test that you performed yourself.
5. Add verified package folder names only after inspecting a legitimately obtained
   archive. Do not guess folder names from listing titles. Multiple folders in
   one listing can share its catalogue ID in the local installation database.
6. Keep the JSON catalogue ID stable when updating it. Add a new catalogue ID for
   an independently maintained collection. Avoid overlapping package IDs between
   active collections; use one catalogue as the canonical owner of each listing.
7. Run `python scripts/validate_catalogues.py` and `python -m pytest -q`.
8. Submit the catalogue change in a PR, or distribute the JSON separately for
   users to load through **Load catalogue JSON**. No new application build is
   needed for local catalogue updates.

Known dependencies and conflicts use manager IDs, not prose names. The engine
checks both directions of conflicts and active dependencies across managed
packages in the same Community directory. A dependency outside this manager
cannot currently be credited automatically; document this limitation clearly.

No general scraper, automatic updater or API downloader is part of v0.1.
Future network integrations must follow the source's approved interface and terms.
