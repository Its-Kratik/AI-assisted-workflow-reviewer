.PHONY: all test eval clean zip

all: test eval

test:
	PYTHONPATH=. python3 -m unittest discover tests -v

eval:
	PYTHONPATH=. python3 evaluate.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	rm -f workflow_reviewer_submission.zip

zip: clean
	zip -r workflow_reviewer_submission.zip . -x "*.git*" "*.zip"
	@echo "Created submission archive: workflow_reviewer_submission.zip"
