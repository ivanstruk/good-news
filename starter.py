
import random
import pandas as pd

from askana.ana import answer_ask_ana

from utils.translator import translate_post_content
from utils.poster import upload_featured_image, post_to_wordpress
from utils.logger import logger

questions = pd.read_csv("askana/questions.csv")
unanswered = questions[questions["dt_answered"].isna() | (questions["dt_answered"] == "")]
unanswered = unanswered["desc_question"].tolist()
random.shuffle(unanswered)

chosen = unanswered[0]
logger.info("Chosen question: {}".format(chosen))

result = answer_ask_ana(chosen)
if result["status"] == "answered":
    body = result["data"]
    post_result = post_to_wordpress(
        title="{}?".format(chosen.split("?")[0]),
        content=body,
        status="publish",
        tags=["advice", "pitanje"],
        categories=["Ask Ana"],
        language="en",                # ensure EN is the canonical source
        translations=None,
    )

else:
    # already_answered | flagged_skip | error
    logger.info(f"{result['status']}: {result['data']}")