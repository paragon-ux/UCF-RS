# Relationship To Reqtrace v2.1.7

Reqtrace v2.1.7 is directionally final in the original repository: one
grep-native marker, one generated ledger, no server, no database, no hidden
authority.

UCF-RS is not Reqtrace v3 and does not replace Reqtrace. It is a separate fork
in architecture for environments that want source-clean citation overlays and
managed edit tracking.

Shared principles:

- stable upstream handles
- explicit evidence acceptance
- append-only audit history
- deterministic generated outputs
- no parser or semantic authority

Architectural differences:

- Reqtrace authority is generated from source markers.
- UCF-RS authority is the durable citation index plus operation log.
- Reqtrace is grep-native in source.
- UCF-RS is grep-native through virtual block/export projections.
