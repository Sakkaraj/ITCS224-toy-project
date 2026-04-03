import json
import os
import tempfile
import unittest

from app import ROOM_TYPES, create_app


class HotelAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bookings_path = os.path.join(self.temp_dir.name, "bookings.json")
        with open(self.bookings_path, "w", encoding="utf-8") as handle:
            json.dump([], handle)

        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "BOOKINGS_FILE": self.bookings_path,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_rejects_invalid_date_order(self) -> None:
        response = self.client.post(
            "/search",
            data={"check_in": "2026-05-10", "check_out": "2026-05-08"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Check-out date must be after check-in date.", response.data)

    def test_search_shows_available_rooms(self) -> None:
        response = self.client.post(
            "/search",
            data={"check_in": "2026-06-10", "check_out": "2026-06-13"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Available rooms", response.data)
        self.assertIn(b"Standard", response.data)

    def test_booking_and_cancellation_flow(self) -> None:
        booking_response = self.client.post(
            "/book",
            data={
                "check_in": "2026-07-10",
                "check_out": "2026-07-12",
                "room_type": "standard",
                "guest_name": "Jamie Carter",
                "guest_email": "jamie@example.com",
            },
            follow_redirects=True,
        )

        self.assertEqual(booking_response.status_code, 200)
        self.assertIn(b"Booking confirmed", booking_response.data)

        with open(self.bookings_path, "r", encoding="utf-8") as handle:
            bookings = json.load(handle)

        self.assertEqual(len(bookings), 1)
        reference = bookings[0]["reference"]

        cancel_response = self.client.post(
            "/cancel",
            data={"reference": reference},
        )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertIn(b"was canceled successfully", cancel_response.data)

        with open(self.bookings_path, "r", encoding="utf-8") as handle:
            bookings_after_cancel = json.load(handle)

        self.assertEqual(bookings_after_cancel, [])

    def test_search_reflects_existing_booking_availability(self) -> None:
        with open(self.bookings_path, "w", encoding="utf-8") as handle:
            json.dump(
                [
                    {
                        "reference": "ABC123",
                        "guest_name": "Existing Guest",
                        "guest_email": "guest@example.com",
                        "room_type": "standard",
                        "room_label": ROOM_TYPES["standard"]["label"],
                        "price_per_night": ROOM_TYPES["standard"]["price"],
                        "check_in": "2026-08-01",
                        "check_out": "2026-08-04",
                        "nights": 3,
                        "total_price": ROOM_TYPES["standard"]["price"] * 3,
                        "created_at": "2026-04-03T00:00:00Z",
                    }
                ],
                handle,
            )

        response = self.client.post(
            "/search",
            data={"check_in": "2026-08-02", "check_out": "2026-08-05"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"2 left", response.data)


if __name__ == "__main__":
    unittest.main()