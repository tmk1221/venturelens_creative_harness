"""post_core: the v3 data model and persistence layer.

See docs/ARCHITECTURE.md. This package intentionally does not import `post_core.workers`
(a separate, concurrently-developed subpackage) from here, to keep this import light and
avoid import-order coupling between the two.
"""
