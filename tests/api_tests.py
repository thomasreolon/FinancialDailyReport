# Test 1
from src.scrapers.news.yt_scraper import YTScraper

def test_fxevolution_scraper():
    result = YTScraper(hours=72, channel='@fxevolutionvideo').scrape()
    assert result is None or (
        isinstance(result, dict)
        and "url" in result
        and "transcript" in result
        and isinstance(result["transcript"], str)
        and len(result["transcript"]) > 0
    )


# Test 2
from src.api.gemini import generate

def test_capital_of_france():
    response = generate("What is the capital of France? Answer in one word.")
    print(f"\n'capital of France?' -> Gemini says: {response.strip()}")
    assert "paris" in response.lower()
    print("OK - response contains 'Paris'")
