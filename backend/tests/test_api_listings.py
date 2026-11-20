import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from backend.app import main
from backend.app.models import Listing


class ListingEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_listing_page_excludes_demo_rows(self) -> None:
        with Session(self.engine) as session:
            live = Listing(
                title="Authorized listing",
                category="Phones",
                asking_price=100000,
                location="Lagos",
                source_name="Approved source",
                is_demo=False,
            )
            demo = Listing(
                title="Demo listing",
                category="Phones",
                asking_price=200000,
                location="Abuja",
                source_name="Demo source",
                is_demo=True,
            )
            session.add_all([live, demo])
            session.commit()

            result = main.list_listings(
                offset=0,
                limit=10,
                category=None,
                city=None,
                location=None,
                listing_status="active",
                session=session,
            )

        self.assertEqual(result.total, 1)
        self.assertEqual([item.title for item in result.items], ["Authorized listing"])


if __name__ == "__main__":
    unittest.main()
