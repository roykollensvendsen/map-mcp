"""A made-up Kartverket that refuses what the real one refuses.

A fake that says yes to everything lets a test pass that the real service would fail. So this
one keeps the service's limits: a search needs a word, and it can be told to stop answering or
to be busy for a while, as the real one can. Write each new limit of a real service in here
first, with a test, before the code that copes with it.

Every place here is made up, and every position sits by 0,0, in the sea, so none can be a
real home.
"""

from __future__ import annotations

from map_mcp.interfaces import BusyError, Place, QueryError, UnreachableError


def made_up(name: str, municipality: str, kind: str = "address", lat: float = 0.01, lon: float = 0.02) -> Place:
    """A made-up place, by default an address, with a position by 0,0."""
    return Place(name=name, municipality=municipality, kind=kind, lat=lat, lon=lon)


#: The fake's own places, when a test names none.
MADE_UP = (
    made_up("Prøvestien 4", "Prøveby"),
    made_up("Prøveby", "Prøveby", "town", 0.0, 0.0),
    made_up("Prøvevatnet", "Prøveby", "lake", 0.03, 0.01),
)


class FakeKartverket:
    """Kartverket's search in memory, with the real one's limits."""

    def __init__(self, places: list[Place] | tuple[Place, ...] = MADE_UP) -> None:
        """Answer from `places`, in their order, which stands for the service's ranking."""
        self.places = list(places)
        self.unreachable = False
        #: Seconds the service says to wait before it is asked again; 0 when it answers.
        self.busy_for = 0.0
        self.asked = 0

    async def find(self, what: str) -> list[Place]:
        """The places whose name holds `what`, whatever its case."""
        self.asked += 1
        if self.unreachable:
            msg = "the address service did not answer"
            raise UnreachableError(msg)
        if self.busy_for:
            raise BusyError(self.busy_for)
        # RULE: the fake refuses an empty search as the address service does
        if not what.strip():
            msg = "a search needs a word to look for"
            raise QueryError(msg)
        wanted = what.strip().casefold()
        return [place for place in self.places if wanted in place.name.casefold()]
