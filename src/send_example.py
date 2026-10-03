from datetime import date

from nonprofit_rooms import InfraiRealtime, NonprofitEvent, publish_event


def main() -> None:
    receipt = NonprofitEvent(
        organization_id="river-aid",
        campaign_id="clean-water-2026",
        kind="donor_receipt",
        subject_id="donor-1042",
        message="Your receipt is ready.",
        effective_on=date(2026, 9, 6),
    )
    delivery = publish_event(InfraiRealtime(), receipt, account_id="river-aid")
    print(f"published {delivery.event} to {delivery.channel}")


if __name__ == "__main__":
    main()
