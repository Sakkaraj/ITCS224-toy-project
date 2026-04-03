# ITCS224 Toy Project

This repository contains a small Flask hotel reservation app. Users can search for available rooms by date, choose a room type, enter guest details, confirm a booking, and cancel an existing booking using the reference number.

## Run Locally

1. Create and activate a virtual environment if you want one.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
flask --app app run --debug
```

4. Open the app in your browser at the address shown by Flask.

## Tests

Run the automated tests with:

```bash
python -m unittest discover -s tests
```

## Storage

Bookings are stored in `bookings.json` in the project root. The app uses local JSON only and does not require a database.# ITCS224-toy-project