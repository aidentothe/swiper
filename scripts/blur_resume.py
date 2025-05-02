import os
import re
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter, ImageDraw

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file"""
    text = ""
    with open(pdf_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text()
    return text

def convert_pdf_to_images(pdf_path, output_folder):
    """Convert PDF pages to images and return paths to the images"""
    # Create output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Convert PDF to images
    images = convert_from_path(pdf_path)
    image_paths = []
    
    for i, image in enumerate(images):
        image_path = f"{output_folder}/page_{i}.png"
        image.save(image_path, "PNG")
        image_paths.append(image_path)
    
    return image_paths

def find_items_to_blur(text, full_name):
    """Find name and links in text"""
    items = []
    
    # Add full name
    items.append(full_name)
    
    # Add individual name parts (only if they're at least 3 characters long)
    name_parts = full_name.split()
    items.extend([part for part in name_parts if len(part) >= 3])
    
    # Find emails
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    items.extend(emails)
    
    # Find LinkedIn URLs
    linkedin = re.findall(r'linkedin\.com/\S+', text)
    items.extend(linkedin)
    
    # Find GitHub URLs
    github = re.findall(r'github\.com/\S+', text)
    items.extend(github)
    
    # Find phone numbers
    phones = re.findall(r'(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', text)
    items.extend(phones)
    
    return items

def find_positions_in_image(image_path, items_to_blur):
    """Find positions of items to blur in the image using OCR"""
    image = Image.open(image_path)
    ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    
    positions = []
    
    # Process each word from OCR
    for i, word in enumerate(ocr_data['text']):
        word = word.strip()
        if not word:
            continue
            
        # Check if this word exactly matches or contains an exact item to blur
        for item in items_to_blur:
            # Skip empty items
            if not item:
                continue
            
            # More precise matching:
            # 1. Exact match for whole word (case insensitive)
            # 2. Word contains the exact item as a distinct part
            
            word_lower = word.lower()
            item_lower = item.lower()
            
            if word_lower == item_lower or (
                item_lower in word_lower and 
                (len(item) >= 4 or 
                 # For shorter items, check if they're distinct parts of the word
                 re.search(r'\b' + re.escape(item_lower) + r'\b', word_lower)
                )
            ):
                x = ocr_data['left'][i]
                y = ocr_data['top'][i]
                width = ocr_data['width'][i]
                height = ocr_data['height'][i]
                
                # Expand the region slightly
                positions.append({
                    'x': max(0, x - 5),
                    'y': max(0, y - 5),
                    'width': width + 10,
                    'height': height + 10
                })
                break
    
    return positions

def blur_image(image_path, positions, output_path):
    """Blur specified positions in the image"""
    image = Image.open(image_path)
    
    for pos in positions:
        # Create a mask for this position
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle([
            pos['x'], 
            pos['y'], 
            pos['x'] + pos['width'], 
            pos['y'] + pos['height']
        ], fill=255)
        
        # Create a blurred version of the image
        blurred = image.filter(ImageFilter.GaussianBlur(15))
        
        # Composite the blurred region onto the original image
        image.paste(blurred, mask=mask)
    
    # Save the modified image
    image.save(output_path)
    return output_path

def blur_pdf(pdf_path, output_pdf_path, full_name):
    """Main function to blur names and links in a PDF"""
    # Create temporary directories
    temp_dir = "temp_images"
    output_dir = "blurred_images"
    
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Extract text and find items to blur
    text = extract_text_from_pdf(pdf_path)
    items_to_blur = find_items_to_blur(text, full_name)
    
    print(f"Found {len(items_to_blur)} items to blur: {items_to_blur}")
    
    # Convert PDF to images
    image_paths = convert_pdf_to_images(pdf_path, temp_dir)
    blurred_images = []
    
    # Process each page
    for i, image_path in enumerate(image_paths):
        print(f"Processing page {i+1}...")
        
        # Find positions to blur
        positions = find_positions_in_image(image_path, items_to_blur)
        print(f"  Found {len(positions)} areas to blur on this page")
        
        # Blur the image
        output_path = f"{output_dir}/blurred_page_{i}.png"
        if positions:
            blur_image(image_path, positions, output_path)
        else:
            # If nothing to blur, just copy the original
            Image.open(image_path).save(output_path)
        
        blurred_images.append(output_path)
    
    # Convert blurred images back to PDF
    images = [Image.open(path) for path in blurred_images]
    if images:
        images[0].save(
            output_pdf_path, 
            "PDF", 
            save_all=True, 
            append_images=images[1:],
            resolution=100.0
        )
    
    print(f"Blurred PDF saved to {output_pdf_path}")
    
    # Clean up
    for path in image_paths + blurred_images:
        if os.path.exists(path):
            os.remove(path)
    
    if os.path.exists(temp_dir):
        os.rmdir(temp_dir)
    if os.path.exists(output_dir):
        os.rmdir(output_dir)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 4:
        print("Usage: python blur_resume.py input.pdf output.pdf \"Full Name\"")
        sys.exit(1)
    
    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]
    full_name = sys.argv[3]
    
    blur_pdf(input_pdf, output_pdf, full_name)