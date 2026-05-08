"""Tests for CBE verifier."""

from datetime import datetime

from tx_verify.services.verify_cbe import _parse_cbe_receipt


def _load_sample_pdf() -> bytes:
    with open("internal/cbe_receipt_FT26125ZD8XR.pdf", "rb") as f:
        return f.read()


def test_parse_cbe_receipt_success() -> None:
    pdf_bytes = _load_sample_pdf()
    result = _parse_cbe_receipt(pdf_bytes)

    assert result.success is True
    assert result.provider == "cbe"
    assert result.transaction_reference == "FT26125ZD8XR"
    assert result.payer_name == "Nahom Dereje Tasew"
    assert result.payer_account == "1****2688"
    assert result.receiver_name == "Meles Diro Bolki"
    assert result.receiver_account == "1****0989"
    assert result.amount == 25.00
    assert result.service_charge == 0.53
    assert result.vat == 0.08
    assert result.total_amount == 25.61
    assert result.amount_in_words == "ETB Twenty Five & Sixty One cents"
    assert result.currency == "ETB"
    assert result.narrative == "Pay done via Mobile"
    assert result.payment_channel == "Mobile"
    assert result.transaction_date == datetime(2026, 5, 5, 13, 56, 0)

    assert result.meta.get("branch") == "MEKANISA MICHAEL BRANC"
    assert result.meta.get("region") == "Adama"
    assert result.meta.get("tin") == "0000006966"


def test_parse_cbe_receipt_invalid_pdf() -> None:
    result = _parse_cbe_receipt(b"not a pdf")
    assert result.success is False
    assert result.provider == "cbe"
    assert "PDF" in (result.error or "")
