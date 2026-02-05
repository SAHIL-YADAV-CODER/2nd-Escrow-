import qrcode
from io import BytesIO

def generate_upi_qr(upi_id: str, payee_name: str, amount: float, transaction_note: str) -> BytesIO:
    """
    Generate UPI QR code data as bytes-like (PNG) using standard UPI URI.
    """
    upi_uri = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount:.2f}&tn={transaction_note}"
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="white", back_color="black")  # dark mode friendly (black bg)
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    return bio