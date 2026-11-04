The proposed framework "IERC" implementational code, utilities, and pilot data is present in IERC-SampleCode-Data.
Note that the full datasets cannot be redistributed due to privacy due to related privacy concerned. 

## Data Collection

We compiled dedicated datasets for **Touristic Experience (TE) recommendation** from **Airbnb, TripAdvisor, and Booking.com** over **2021–2023**, as no suitable public dataset was available for this task.

Data collection covered seven tourism destinations: **Rome, Paris, Madrid, London, New York, Berlin, and Barcelona**.

### Collection and Processing

1. **Dataset organisation:** Separate TE and user datasets were maintained for each platform and destination.
2.**TE data:** TE data included available profile attributes such as title, description, location, rating, number of reviews, number of photos, video availability, price, included services or items, host description, location description, and associated reviews.
3. **Review filtering:** User records were derived from publicly available reviews. Only non-anonymous, English-language reviews were retained.
4. **User data:** Each unique username within a platform was assigned an internal masked user ID. Reviews from the same username on that platform shared the same ID; accounts across platforms were treated separately.
5. **Pseudonymisation:** Usernames were not retained in the resulting user records. Any personal profile information, including names, locations, biographies, and photos, was excluded.
6. **Retained attributes:** User records included the internal masked user ID and available review text, title, date, time, rating, and associated TE identifier.
7. **Source-level aggregation:** Records from all seven destinations were combined into one user dataset and one TE dataset per platform, forming three source-specific knowledge bases.