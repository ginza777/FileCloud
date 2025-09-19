import re
import requests
from django.conf import settings
from apps.files.models import SiteToken
import logging

logger = logging.getLogger(__name__)

def refresh_soff_token():
    """
    Refreshes the SOFF website token (buildId) by scraping it from the website.
    Returns the new token if successful, None if failed.
    """
    try:
        page_url = "https://soff.uz/scientific-resources/all?slug=all&search="
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

        # Get the page
        r = session.get(page_url)
        r.raise_for_status()
        html = r.text

        # Find buildId
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if not m:
            m = re.search(r'"buildId":"([^"]+)"', html)

        if not m:
            logger.error("Failed to find buildId in the page content")
            return None

        build_id = m.group(1)

        # Update or create token in database
        site_token, created = SiteToken.objects.update_or_create(
            name='soff',  # Changed from site_name to name
            defaults={'token': build_id}
        )

        logger.info(f"Successfully {'created' if created else 'updated'} SOFF token: {build_id}")
        return build_id

    except requests.RequestException as e:
        logger.error(f"Network error while refreshing SOFF token: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while refreshing SOFF token: {str(e)}")
        return None

def get_valid_soff_token():
    """
    Gets a valid SOFF token, refreshing it if necessary.
    Returns the token if successful, None if failed.
    """
    try:
        # Try to get existing token
        site_token = SiteToken.objects.filter(name='soff').first()  # Changed from site_name to name

        if site_token:
            # Verify token is still valid
            session = requests.Session()
            session.headers.update({"User-Agent": "Mozilla/5.0"})

            json_url = f"https://soff.uz/_next/data/{site_token.token}/scientific-resources/all.json?slug=all&search="
            resp = session.get(json_url)

            if resp.status_code == 200:
                return site_token.token

        # If we get here, either there's no token or it's invalid
        return refresh_soff_token()

    except Exception as e:
        logger.error(f"Error checking/getting SOFF token: {str(e)}")
        return None
