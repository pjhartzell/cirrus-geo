# Open questions

Unresolved items parked during the docs overhaul (see DOCS_PLAN.md). Each needs
a decision — fill with verified content or delete — rather than silent
retention.

## Empty section headers with no covering Session-2 task

Pre-existing content gaps (present in the RST before conversion; conversion was
content-neutral so they carried over). 40_config-deploy's empty headers are
covered by task 2.2 and 80_monitoring's by task 2.3; the following are not
covered by any planned task:

| Location | Empty section |
|----------|---------------|
| `docs/src/cirrus/10_intro.md:16` | Why Cirrus? |
| `docs/src/cirrus/20_arch.md:67` | Naming conventions |
| `docs/src/cirrus/50_operation.md:3-23` | Process definition (+ 4 subsections), Managing Secrets for Bucket access, Submit a job for processing, Check statedb, Go to workflow (Step Function execution), Inspect output STAC Items — 9 leaf sections |
| `docs/src/cirrus/components/feeders/index.md:12,16,18` | Lambda, Batch, Local? · Process definition · Creating new feeder |
| `docs/src/cirrus/components/tasks/batch.md:511` | Managing changes to Batch resources |
