Goal 0: Refactor fearlessly
Goal 1: Unit test on submit
Goal 2: CI/CD (really just for fun)
Other stuff: type annotations, pylint on submit

TODO not complete!

I'd like to know
  * integ with external things ~works
	* pennant chase scrape
	  * detects new games ... and stabilizes
	* pennant chase post
	* firestore
	* gcs
  * end-to-end?
    * preferably with no or minimal mocks/fakes
	* for this don't use archive storage class since objects are short-lived
	* for starters use one of my sandbox leagues and clear (let's say) one game
	* avoid backfill though
  * corner cases (unit not integration)
    * scrape mid-day
