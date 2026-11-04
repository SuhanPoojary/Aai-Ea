from notifications import send_notification


def test_notification_uses_test_transport():
    sent = []

    def transport(message):
        sent.append(message)

    assert send_notification(
        "customer@example.test",
        "Ticket",
        "Created",
        transport=transport,
    )
    assert sent[0]["To"] == "customer@example.test"


def test_notification_failure_does_not_raise():
    def transport(_message):
        raise OSError("test transport failure")

    assert send_notification(
        "customer@example.test",
        "Ticket",
        "Created",
        transport=transport,
    ) is False
