# trinetra-core

The portable, platform-agnostic core runtime for **TRINETRA v2 (त्रिनेत्र)**.

## Architectural Mandate
- **Zero OS-Specific Imports:** Core contains pure business logic, event dispatching, and policy enforcement.
- **Hardware Abstraction Layer (HAL):** Interfaces for camera, audio in/out, GPS/location, comms (SMS), and storage.
- **Protocol Schema v2.0:** Typed, versioned events with priority routing and optional cryptographic tamper-evidence.
- **Tiered Capability Negotiation:** Dynamically scales between `FULL`, `STANDARD`, and `LITE` operating profiles based on device hardware and thermal/battery constraints.
