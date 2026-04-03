from __future__ import annotations

import json
import os
import secrets
import string
from datetime import date, datetime, timezone

from flask import Flask, abort, render_template, request, redirect, url_for


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BOOKINGS_FILE = os.path.join(BASE_DIR, "bookings.json")

ROOM_TYPES = {
	"standard": {"label": "Standard", "price": 120, "inventory": 3},
	"deluxe": {"label": "Deluxe", "price": 180, "inventory": 2},
	"suite": {"label": "Suite", "price": 260, "inventory": 1},
}

DATE_FORMAT = "%Y-%m-%d"
REFERENCE_LENGTH = 6


def ensure_bookings_file(path: str) -> None:
	directory = os.path.dirname(path)
	if directory:
		os.makedirs(directory, exist_ok=True)
	if not os.path.exists(path):
		with open(path, "w", encoding="utf-8") as handle:
			json.dump([], handle, indent=2)


def load_bookings(path: str) -> list[dict]:
	ensure_bookings_file(path)
	try:
		with open(path, "r", encoding="utf-8") as handle:
			data = json.load(handle)
	except json.JSONDecodeError:
		return []

	if isinstance(data, list):
		return data
	return []


def save_bookings(path: str, bookings: list[dict]) -> None:
	directory = os.path.dirname(path)
	if directory:
		os.makedirs(directory, exist_ok=True)

	temp_path = f"{path}.tmp"
	with open(temp_path, "w", encoding="utf-8") as handle:
		json.dump(bookings, handle, indent=2)
	os.replace(temp_path, path)


def parse_date(raw_value: str | None) -> date | None:
	if not raw_value:
		return None
	try:
		return datetime.strptime(raw_value, DATE_FORMAT).date()
	except ValueError:
		return None


def format_date(value: date) -> str:
	return value.strftime("%B %d, %Y")


def format_currency(value: int | float) -> str:
	return f"${value:,.2f}"


def normalize_reference(reference: str | None) -> str:
	return (reference or "").strip().upper()


def calculate_nights(check_in: date, check_out: date) -> int:
	return (check_out - check_in).days


def bookings_overlap(existing: dict, check_in: date, check_out: date) -> bool:
	existing_check_in = parse_date(existing.get("check_in"))
	existing_check_out = parse_date(existing.get("check_out"))
	if existing_check_in is None or existing_check_out is None:
		return False
	return check_in < existing_check_out and check_out > existing_check_in


def existing_references(bookings: list[dict]) -> set[str]:
	return {normalize_reference(booking.get("reference")) for booking in bookings if booking.get("reference")}


def generate_reference(bookings: list[dict]) -> str:
	taken = existing_references(bookings)
	alphabet = string.ascii_uppercase + string.digits
	while True:
		candidate = "".join(secrets.choice(alphabet) for _ in range(REFERENCE_LENGTH))
		if candidate not in taken:
			return candidate


def available_rooms(bookings: list[dict], room_type: str, check_in: date, check_out: date) -> int:
	room_config = ROOM_TYPES[room_type]
	overlapping = sum(
		1
		for booking in bookings
		if booking.get("room_type") == room_type and bookings_overlap(booking, check_in, check_out)
	)
	return max(room_config["inventory"] - overlapping, 0)


def availability_snapshot(bookings: list[dict], check_in: date, check_out: date) -> dict[str, dict]:
	snapshot: dict[str, dict] = {}
	for room_type, room_config in ROOM_TYPES.items():
		remaining = available_rooms(bookings, room_type, check_in, check_out)
		nights = calculate_nights(check_in, check_out)
		snapshot[room_type] = {
			"label": room_config["label"],
			"price": room_config["price"],
			"inventory": room_config["inventory"],
			"available": remaining,
			"nights": nights,
			"total": room_config["price"] * nights,
		}
	return snapshot


def validate_date_range(check_in_raw: str | None, check_out_raw: str | None) -> tuple[date | None, date | None, list[str]]:
	errors: list[str] = []
	check_in = parse_date(check_in_raw)
	check_out = parse_date(check_out_raw)

	if check_in is None:
		errors.append("Enter a valid check-in date.")
	if check_out is None:
		errors.append("Enter a valid check-out date.")
	if check_in and check_out:
		if check_in >= check_out:
			errors.append("Check-out date must be after check-in date.")
		if check_in < date.today():
			errors.append("Check-in date cannot be in the past.")

	return check_in, check_out, errors


def find_booking(bookings: list[dict], reference: str) -> dict | None:
	target = normalize_reference(reference)
	for booking in bookings:
		if normalize_reference(booking.get("reference")) == target:
			return booking
	return None


def create_app(test_config: dict | None = None) -> Flask:
	app = Flask(__name__)
	app.config.from_mapping(
		SECRET_KEY="dev",
		BOOKINGS_FILE=DEFAULT_BOOKINGS_FILE,
	)
	if test_config:
		app.config.update(test_config)

	ensure_bookings_file(app.config["BOOKINGS_FILE"])

	@app.template_filter("currency")
	def currency_filter(value: int | float) -> str:
		return format_currency(value)

	@app.template_filter("friendly_date")
	def friendly_date_filter(value: str) -> str:
		parsed = parse_date(value)
		return format_date(parsed) if parsed else value

	@app.get("/")
	def index() -> str:
		return render_template(
			"index.html",
			errors=[],
			search_form={"check_in": "", "check_out": ""},
			search_results=None,
			search_summary=None,
			today=date.today().isoformat(),
		)

	@app.post("/search")
	def search() -> str:
		check_in_raw = request.form.get("check_in")
		check_out_raw = request.form.get("check_out")
		check_in, check_out, errors = validate_date_range(check_in_raw, check_out_raw)

		if errors or check_in is None or check_out is None:
			return render_template(
				"index.html",
				errors=errors,
				search_form={"check_in": check_in_raw or "", "check_out": check_out_raw or ""},
				search_results=None,
				search_summary=None,
				today=date.today().isoformat(),
			)

		bookings = load_bookings(app.config["BOOKINGS_FILE"])
		results = availability_snapshot(bookings, check_in, check_out)
		return render_template(
			"index.html",
			errors=[],
			search_form={"check_in": check_in_raw or "", "check_out": check_out_raw or ""},
			search_results=results,
			search_summary={
				"check_in": format_date(check_in),
				"check_out": format_date(check_out),
				"nights": calculate_nights(check_in, check_out),
			},
			today=date.today().isoformat(),
		)

	@app.get("/book")
	def book_form() -> str:
		room_type = request.args.get("room_type", "")
		check_in_raw = request.args.get("check_in")
		check_out_raw = request.args.get("check_out")
		check_in, check_out, errors = validate_date_range(check_in_raw, check_out_raw)

		if room_type not in ROOM_TYPES:
			errors.append("Choose a room type from the search results.")

		if errors or check_in is None or check_out is None:
			return render_template(
				"index.html",
				errors=errors,
				search_form={"check_in": check_in_raw or "", "check_out": check_out_raw or ""},
				search_results=None,
				search_summary=None,
				today=date.today().isoformat(),
			)

		bookings = load_bookings(app.config["BOOKINGS_FILE"])
		remaining = available_rooms(bookings, room_type, check_in, check_out)
		if remaining <= 0:
			return render_template(
				"index.html",
				errors=["That room type is no longer available for the selected dates."],
				search_form={"check_in": check_in_raw or "", "check_out": check_out_raw or ""},
				search_results=availability_snapshot(bookings, check_in, check_out),
				search_summary={
					"check_in": format_date(check_in),
					"check_out": format_date(check_out),
					"nights": calculate_nights(check_in, check_out),
				},
				today=date.today().isoformat(),
			)

		room = ROOM_TYPES[room_type]
		return render_template(
			"book.html",
			room_type=room_type,
			room=room,
			check_in=check_in_raw,
			check_out=check_out_raw,
			check_in_display=format_date(check_in),
			check_out_display=format_date(check_out),
			nights=calculate_nights(check_in, check_out),
			total=room["price"] * calculate_nights(check_in, check_out),
		)

	@app.post("/book")
	def create_booking() -> str:
		guest_name = (request.form.get("guest_name") or "").strip()
		guest_email = (request.form.get("guest_email") or "").strip()
		room_type = (request.form.get("room_type") or "").strip()
		check_in_raw = request.form.get("check_in")
		check_out_raw = request.form.get("check_out")

		check_in, check_out, errors = validate_date_range(check_in_raw, check_out_raw)

		if room_type not in ROOM_TYPES:
			errors.append("Select a valid room type.")
		if not guest_name:
			errors.append("Enter the guest name.")
		if not guest_email or "@" not in guest_email:
			errors.append("Enter a valid email address.")

		bookings = load_bookings(app.config["BOOKINGS_FILE"])

		if check_in and check_out and room_type in ROOM_TYPES:
			remaining = available_rooms(bookings, room_type, check_in, check_out)
			if remaining <= 0:
				errors.append("That room type is no longer available for the selected dates.")

		if errors or check_in is None or check_out is None or room_type not in ROOM_TYPES:
			if room_type not in ROOM_TYPES or check_in is None or check_out is None:
				return render_template(
					"index.html",
					errors=errors,
					search_form={"check_in": check_in_raw or "", "check_out": check_out_raw or ""},
					search_results=None,
					search_summary=None,
					today=date.today().isoformat(),
				)

			return render_template(
				"book.html",
				room_type=room_type,
				room=ROOM_TYPES.get(room_type),
				check_in=check_in_raw,
				check_out=check_out_raw,
				check_in_display=format_date(check_in) if check_in else check_in_raw,
				check_out_display=format_date(check_out) if check_out else check_out_raw,
				nights=calculate_nights(check_in, check_out) if check_in and check_out else None,
				total=(ROOM_TYPES.get(room_type, {}).get("price", 0) * calculate_nights(check_in, check_out)) if check_in and check_out and room_type in ROOM_TYPES else None,
				errors=errors,
				guest_name=guest_name,
				guest_email=guest_email,
			)

		reference = generate_reference(bookings)
		room = ROOM_TYPES[room_type]
		nights = calculate_nights(check_in, check_out)
		booking = {
			"reference": reference,
			"guest_name": guest_name,
			"guest_email": guest_email,
			"room_type": room_type,
			"room_label": room["label"],
			"price_per_night": room["price"],
			"check_in": check_in.isoformat(),
			"check_out": check_out.isoformat(),
			"nights": nights,
			"total_price": room["price"] * nights,
			"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
		}
		bookings.append(booking)
		save_bookings(app.config["BOOKINGS_FILE"], bookings)

		return redirect(url_for("confirmation", reference=reference))

	@app.get("/confirmation/<reference>")
	def confirmation(reference: str) -> str:
		bookings = load_bookings(app.config["BOOKINGS_FILE"])
		booking = find_booking(bookings, reference)
		if booking is None:
			abort(404)

		room = ROOM_TYPES[booking["room_type"]]
		return render_template("confirmation.html", booking=booking, room=room)

	@app.get("/cancel")
	def cancel_form() -> str:
		return render_template("cancel.html", result=None, reference="", errors=[])

	@app.post("/cancel")
	def cancel_booking() -> str:
		reference = normalize_reference(request.form.get("reference"))
		errors: list[str] = []
		if not reference:
			errors.append("Enter a booking reference number.")
			return render_template("cancel.html", result=None, reference="", errors=errors)

		bookings = load_bookings(app.config["BOOKINGS_FILE"])
		booking = find_booking(bookings, reference)
		if booking is None:
			return render_template(
				"cancel.html",
				result={"status": "error", "message": f"No booking was found for reference {reference}."},
				reference=reference,
				errors=[],
			)

		updated_bookings = [entry for entry in bookings if normalize_reference(entry.get("reference")) != reference]
		save_bookings(app.config["BOOKINGS_FILE"], updated_bookings)

		return render_template(
			"cancel.html",
			result={
				"status": "success",
				"message": f"Booking {reference} was canceled successfully.",
				"booking": booking,
			},
			reference="",
			errors=[],
		)

	@app.errorhandler(404)
	def not_found(_error: Exception) -> tuple[str, int]:
		return render_template("404.html"), 404

	return app


app = create_app()


if __name__ == "__main__":
	app.run(debug=True)
