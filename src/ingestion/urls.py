"""Host comparison shared by the feed and listing paths.

Both answer the same question: does this URL still belong to the publisher we
believe we are reading? The listing path asks it of a redirect, the feed path of an
entry's link. Getting it wrong in either place attributes an item to a source that
never published it, and inflates the source diversity section 15 reads as
corroboration.
"""

from __future__ import annotations

from urllib.parse import urlparse


def registrable(host: str) -> str:
    """Enough of a host to tell one organisation from another.

    Not a public-suffix implementation: it keeps the last three labels for a
    two-part TLD like .co.uk and the last two otherwise, which is sufficient to
    catch a link that leaves the publisher behind.
    """
    labels = host.lower().split(":")[0].strip(".").split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and len(labels[-2]) <= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def same_site(left: str, right: str) -> bool:
    return registrable(urlparse(left).netloc) == registrable(urlparse(right).netloc)
