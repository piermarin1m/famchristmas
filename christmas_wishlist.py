import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
import json
import time
from pymongo import MongoClient
from pymongo.server_api import ServerApi

st.set_page_config(
    page_title="Family Christmas Wishlist 🎄",
    page_icon="🎁",
    layout="wide"
)

# Custom CSS for styling
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 16px;
    }
    div[data-testid="stForm"] {
        border: 1px solid #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
    }
    div.row-widget.stButton button {
        width: 100%;
        border-radius: 5px;
        height: 45px;
        font-size: 16px;
    }
</style>
""", unsafe_allow_html=True)

MONGO_URI = "mongodb+srv://piermarinim:Matteo#3@christmas.ka3gx.mongodb.net/"
try:
    client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    db = client['christmas']
    # Create collections for each person if they don't exist
    people = ["Matteo", "Nicolas", "Aria", "Mom", "Dad", "Kyle", "Julia"]
    collections = {person: db[person.lower()] for person in people}
    # Verify connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
except Exception as e:
    st.error(f"Failed to connect to MongoDB: {str(e)}")
    print(f"MongoDB connection error: {str(e)}")

# Initialize session state for storing wishlists
if 'wishlists' not in st.session_state:
    st.session_state.wishlists = {
        name: [] for name in ["Matteo", "Nicolas", "Aria", "Mom", "Dad", "Julia", "Kyle"]
    }

def scrape_product_details(url):
    """Enhanced scraper with specific support for major retailers"""
    try:
        session = requests.Session()
        
        # Handle redirects (for shortened URLs)
        response = session.get(url, allow_redirects=True)
        url = response.url
        domain = urlparse(url).netloc

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }

        response = session.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        product_data = {
            'name': '',
            'price': 0.0,
            'image_url': '',
            'description': '',
            'brand': ''
        }

        # Walmart-specific scraping
        if 'walmart.com' in domain:
            # Try to get data from JSON-LD script
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if '@type' in data and data['@type'] == 'Product':
                        product_data['name'] = data.get('name', '')
                        if 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, list):
                                offers = offers[0]
                            if isinstance(offers, dict):
                                product_data['price'] = float(offers.get('price', 0))
                        product_data['image_url'] = data.get('image', '')
                        break
                except:
                    continue
            
            # Fallback to HTML elements
            if not product_data['name']:
                name_elem = soup.find('h1', {'itemprop': 'name'}) or soup.find('h1', {'data-testid': 'product-title'})
                if name_elem:
                    product_data['name'] = name_elem.text.strip()
            
            if not product_data['price']:
                price_elem = soup.find('span', {'itemprop': 'price'}) or soup.select_one('[data-testid="price-wrap"] span')
                if price_elem:
                    try:
                        price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                        product_data['price'] = float(re.findall(r'\d+\.?\d*', price_text)[0])
                    except:
                        pass

            if not product_data['image_url']:
                img_elem = soup.find('img', {'data-testid': 'hero-image'})
                if img_elem:
                    product_data['image_url'] = img_elem.get('src', '')

        # Target-specific scraping
        elif 'target.com' in domain:
            # Try to get data from meta tags first
            meta_title = soup.find('meta', {'property': 'og:title'})
            if meta_title:
                product_data['name'] = meta_title.get('content', '')

            meta_image = soup.find('meta', {'property': 'og:image'})
            if meta_image:
                product_data['image_url'] = meta_image.get('content', '')

            # Try to get price from JSON data
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and 'price' in str(data):
                        price_matches = re.findall(r'"price":\s*{\s*"current":\s*(\d+\.?\d*)', str(data))
                        if price_matches:
                            product_data['price'] = float(price_matches[0])
                            break
                except:
                    continue

            # Fallback to HTML elements
            if not product_data['name']:
                name_elem = soup.find('h1', {'data-test': 'product-title'})
                if name_elem:
                    product_data['name'] = name_elem.text.strip()

            if not product_data['price']:
                price_elem = soup.select_one('[data-test="product-price"]')
                if price_elem:
                    try:
                        price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                        product_data['price'] = float(re.findall(r'\d+\.?\d*', price_text)[0])
                    except:
                        pass

        # Sephora-specific scraping
        elif 'sephora.com' in domain:
            meta_title = soup.find('meta', {'property': 'og:title'})
            if meta_title:
                product_data['name'] = meta_title.get('content', '').split('|')[0].strip()

            meta_image = soup.find('meta', {'property': 'og:image'})
            if meta_image:
                product_data['image_url'] = meta_image.get('content', '')

            # Try to get price from JSON data
            scripts = soup.find_all('script', type='application/json')
            for script in scripts:
                try:
                    if 'currentSku' in script.string:
                        data = json.loads(script.string)
                        price_matches = re.findall(r'"listPrice":\s*"?\$?(\d+\.?\d*)"?', str(data))
                        if price_matches:
                            product_data['price'] = float(price_matches[0])
                            break
                except:
                    continue

            # Fallback to HTML elements
            if not product_data['price']:
                price_elem = soup.select_one('[data-comp="Price "]')
                if price_elem:
                    try:
                        price_text = price_elem.text.strip().replace('$', '').replace(',', '')
                        product_data['price'] = float(re.findall(r'\d+\.?\d*', price_text)[0])
                    except:
                        pass

        # Generic scraping for other sites
        else:
            # Try JSON-LD
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        data = next((item for item in data if item.get('@type') == 'Product'), None)
                    if data and data.get('@type') == 'Product':
                        product_data['name'] = data.get('name', '')
                        if 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, list):
                                offers = offers[0]
                            if isinstance(offers, dict):
                                product_data['price'] = float(offers.get('price', 0))
                        product_data['image_url'] = data.get('image', '')
                        if isinstance(product_data['image_url'], list):
                            product_data['image_url'] = product_data['image_url'][0]
                        break
                except:
                    continue

            # Try meta tags if JSON-LD failed
            if not product_data['name']:
                meta_title = soup.find('meta', {'property': 'og:title'})
                if meta_title:
                    product_data['name'] = meta_title.get('content', '')

            if not product_data['image_url']:
                meta_image = soup.find('meta', {'property': 'og:image'})
                if meta_image:
                    product_data['image_url'] = meta_image.get('content', '')

            if not product_data['price']:
                # Try common price patterns
                price_patterns = [
                    r'\$\s*(\d+(?:,\d{3})*\.?\d*)',
                    r'USD\s*(\d+(?:,\d{3})*\.?\d*)',
                    r'Price:\s*\$?(\d+(?:,\d{3})*\.?\d*)',
                ]
                
                for pattern in price_patterns:
                    price_matches = re.findall(pattern, response.text)
                    if price_matches:
                        try:
                            price_text = price_matches[0].replace(',', '')
                            product_data['price'] = float(price_text)
                            break
                        except:
                            continue

        # Clean up the data
        if product_data['name']:
            product_data['name'] = ' '.join(product_data['name'].split())
            product_data['name'] = product_data['name'][:200]
        
        if product_data['image_url']:
            product_data['image_url'] = product_data['image_url'].replace('http://', 'https://')
            product_data['image_url'] = re.sub(r'\?.*$', '', product_data['image_url'])

        # Final validation
        if not product_data['name']:
            st.error("Could not extract product details. Please check the link and try again.")
            return None

        return product_data

    except Exception as e:
        st.error(f"Error scraping product details: {str(e)}")
        return None

def add_gift(person, gift_name, gift_link, gift_price, gift_priority, image_url=""):
    """Add a gift to a person's wishlist and their MongoDB collection"""
    gift = {
        'name': gift_name,
        'link': gift_link,
        'price': gift_price,
        'priority': gift_priority,
        'image_url': image_url,
        'date_added': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Add to session state
    st.session_state.wishlists[person].append(gift)
    
    # Add to MongoDB using person's collection
    try:
        collections[person].insert_one(gift)
    except Exception as e:
        st.error(f"Failed to save to database: {str(e)}")


def delete_gift(person, index):
    """Delete a gift from a person's wishlist and their MongoDB collection"""
    try:
        # Get the gift to be deleted
        gift = st.session_state.wishlists[person][index]
        
        # Delete from MongoDB using person's collection
        collections[person].delete_one({
            'name': gift['name'],
            'link': gift['link'],
            'date_added': gift['date_added']
        })
        
        # Delete from session state
        st.session_state.wishlists[person].pop(index)
    except Exception as e:
        st.error(f"Failed to delete from database: {str(e)}")

def load_wishlist_data():
    """Load wishlist data from MongoDB collections"""
    try:
        # Clear current session state
        st.session_state.wishlists = {
            name: [] for name in ["Matteo", "Nicolas", "Aria", "Mom", "Dad", "Julia", "Kyle"]
        }
        
        # Load data from each person's collection
        for person in st.session_state.wishlists.keys():
            items = collections[person].find({})
            for item in items:
                # Remove MongoDB _id before adding to session state
                item.pop('_id', None)
                st.session_state.wishlists[person].append(item)
    except Exception as e:
        st.error(f"Failed to load data from database: {str(e)}")

# Add this right after initializing session state
# Load data from MongoDB when the app starts
if 'wishlists' in st.session_state:
    load_wishlist_data()

# Main app header
st.title("🎄 Family Christmas Wishlist 2024")
st.markdown("---")

# Create tabs for each family member
tabs = st.tabs(["Matteo", "Nicolas", "Aria", "Mom", "Dad", "Julia", "Kyle"])

for i, (person, tab) in enumerate(zip(st.session_state.wishlists.keys(), tabs)):
    with tab:
        st.header(f"{person}'s Wishlist")
        
        # Add gift form
        with st.form(key=f"add_gift_form_{person}"):
            st.subheader("Add a Gift 🎁")
            
            # URL input
            gift_link = st.text_input("Product Link (optional)", key=f"link_{person}")
            
            cols = st.columns([2, 1])
            
            if gift_link:
                # Auto-fill button
                if cols[1].form_submit_button("Auto-fill from Link"):
                    with st.spinner("Fetching product details..."):
                        try:
                            product_data = scrape_product_details(gift_link)
                            if product_data and product_data['name']:
                                st.session_state[f"name_{person}"] = product_data['name']
                                st.session_state[f"price_{person}"] = product_data['price']
                                st.session_state[f"image_{person}"] = product_data['image_url']
                                st.success("Product details fetched successfully!")
                            else:
                                st.error("Couldn't fetch product details. Please enter manually.")
                        except Exception as e:
                            st.error(f"Error fetching details: {str(e)}")
            
            # Manual input fields
            gift_name = st.text_input(
                "Gift Name *", 
                value=st.session_state.get(f"name_{person}", ""),
                key=f"name_input_{person}"
            )
            
            cols = st.columns([1, 1, 1])
            
            gift_price = cols[0].number_input(
                "Price *", 
                min_value=0.0, 
                value=float(st.session_state.get(f"price_{person}", 0.0)),
                key=f"price_input_{person}"
            )
            
            gift_priority = cols[1].selectbox(
                "Priority *",
                ["High ⭐⭐⭐", "Medium ⭐⭐", "Low ⭐"],
                key=f"priority_{person}"
            )
            
            image_url = st.text_input(
                "Image URL (optional)", 
                value=st.session_state.get(f"image_{person}", ""),
                key=f"image_input_{person}"
            )
            
            # Submit button
            submitted = st.form_submit_button("Add to Wishlist", use_container_width=True)
            
        # Handle form submission outside the form
        if submitted:
            try:
                # Validate required fields
                if not gift_name:
                    st.error("Please enter a gift name!")
                    st.stop()  # Use st.stop() instead of return
                
                if gift_price < 0:
                    st.error("Price cannot be negative!")
                    st.stop()  # Use st.stop() instead of return
                
                # Clean up the link
                if gift_link and not (gift_link.startswith('http://') or gift_link.startswith('https://')):
                    gift_link = 'https://' + gift_link
                
                # Clean up the image URL
                if image_url and not (image_url.startswith('http://') or image_url.startswith('https://')):
                    image_url = 'https://' + image_url
                
                # Validate image URL format if provided
                if image_url:
                    try:
                        response = requests.head(image_url)
                        content_type = response.headers.get('content-type', '')
                        if not content_type.startswith('image/'):
                            st.warning("The provided URL doesn't seem to be an image. Using default image instead.")
                            image_url = ""
                    except:
                        st.warning("Couldn't validate image URL. Using default image instead.")
                        image_url = ""
                
                # Add the gift
                add_gift(
                    person=person,
                    gift_name=gift_name.strip(),
                    gift_link=gift_link.strip() if gift_link else "",
                    gift_price=float(gift_price),
                    gift_priority=gift_priority,
                    image_url=image_url.strip() if image_url else ""
                )
                
                # Clear session state
                for key in [f"name_{person}", f"price_{person}", f"image_{person}"]:
                    if key in st.session_state:
                        del st.session_state[key]
                
                # Show success message and refresh
                st.success("Gift added successfully! 🎁")
                st.balloons()  # Add a fun animation
                st.rerun()
                
            except Exception as e:
                st.error(f"Error adding gift: {str(e)}")
                st.error("Please try again or contact support if the problem persists.")

        # Modify the display section to show images
        st.markdown("### My Wishlist Items")
        if not st.session_state.wishlists[person]:
            st.info("No items in wishlist yet!")
        else:
            for idx, gift in enumerate(st.session_state.wishlists[person]):
                with st.container():
                    if gift['image_url']:
                        cols = st.columns([1, 3, 1, 1, 1])
                        cols[0].image(gift['image_url'], width=100)
                        
                        # Gift name and link
                        if gift['link']:
                            cols[1].markdown(f"**{gift['name']}** ([Link]({gift['link']})) ")
                        else:
                            cols[1].markdown(f"**{gift['name']}**")
                        
                        # Price
                        cols[2].markdown(f"${gift['price']:.2f}")
                        
                        # Priority
                        cols[3].markdown(f"{gift['priority']}")
                        
                        # Delete button
                        if cols[4].button("🗑️", key=f"delete_{person}_{idx}"):
                            delete_gift(person, idx)
                            st.rerun()
                    else:
                        cols = st.columns([3, 1, 1, 1])
                        
                        # Gift name and link
                        if gift['link']:
                            cols[0].markdown(f"**{gift['name']}** ([Link]({gift['link']})) ")
                        else:
                            cols[0].markdown(f"**{gift['name']}**")
                        
                        # Price
                        cols[1].markdown(f"${gift['price']:.2f}")
                        
                        # Priority
                        cols[2].markdown(f"{gift['priority']}")
                        
                        # Delete button
                        if cols[3].button("🗑️", key=f"delete_{person}_{idx}"):
                            delete_gift(person, idx)
                            st.rerun()
                
                st.markdown("---")

# Footer
st.markdown("---")
st.markdown(
    f"""
    <div style='text-align: center'>
        <p>Last updated: {datetime.now().strftime("%B %d, %Y")}</p>
    </div>
    """,
    unsafe_allow_html=True
)
