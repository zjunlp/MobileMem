from membase.model_types.dataset import QuestionAnswerPair


def filter_adversarial(qa_pair: QuestionAnswerPair) -> bool:
    """Keep all question types except adversarial."""
    return qa_pair.metadata.get("question_type") != "adversarial"
