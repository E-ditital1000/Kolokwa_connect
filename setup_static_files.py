"""
Automated Static Files Setup for Kolokwa Connect
This script downloads required libraries into your existing static folder structure
"""

import os
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'Kolokwa_connect' / 'static'

print("=" * 70)
print("Kolokwa Connect - Static Files Setup")
print("=" * 70)
print(f"Base directory: {BASE_DIR}")
print(f"Static directory: {STATIC_DIR}")
print(f"Static directory exists: {STATIC_DIR.exists()}")
print("=" * 70)

# CDN URLs for libraries
DOWNLOADS = {
    # Owl Carousel
    'lib/owlcarousel/owl.carousel.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/OwlCarousel2/2.3.4/owl.carousel.min.js',
    'lib/owlcarousel/assets/owl.carousel.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/OwlCarousel2/2.3.4/assets/owl.carousel.min.css',
    'lib/owlcarousel/assets/owl.theme.default.min.css': 'https://cdnjs.cloudflare.com/ajax/libs/OwlCarousel2/2.3.4/assets/owl.theme.default.min.css',
    
    # Easing
    'lib/easing/easing.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/jquery-easing/1.4.1/jquery.easing.min.js',
    
    # Waypoints
    'lib/waypoints/waypoints.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/waypoints/4.0.1/jquery.waypoints.min.js',
    
    # CounterUp
    'lib/counterup/counterup.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/Counter-Up/1.0.0/jquery.counterup.min.js',
}

def download_file(url, destination):
    """Download a file from URL to destination"""
    try:
        print(f"  Downloading {destination.name}... ", end='', flush=True)
        
        # Create a request with a user agent to avoid blocking
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
        with urllib.request.urlopen(req) as response:
            content = response.read()
            destination.write_bytes(content)
        
        size = destination.stat().st_size
        print(f"✓ ({size:,} bytes)")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def create_style_css():
    """Create the main style.css file"""
    css_content = '''/* Kolokwa Connect - Main Stylesheet */

/* ============================================================================
   ROOT VARIABLES
   ============================================================================ */
:root {
    --primary: #1a56db;
    --secondary: #ff6b35;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --info: #3b82f6;
    --light: #f9fafb;
    --dark: #1f2937;
    --border-light: #e5e7eb;
}

/* ============================================================================
   GLOBAL STYLES
   ============================================================================ */
body {
    font-family: 'Open Sans', sans-serif;
    color: var(--dark);
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Jost', sans-serif;
    font-weight: 600;
}

/* ============================================================================
   NAVBAR
   ============================================================================ */
.navbar {
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.navbar-brand {
    font-weight: 700;
}

.navbar-light .navbar-nav .nav-link {
    color: var(--dark);
    font-weight: 500;
    padding: 0.5rem 1rem;
    transition: all 0.3s;
}

.navbar-light .navbar-nav .nav-link:hover,
.navbar-light .navbar-nav .nav-link.active {
    color: var(--primary);
}

/* ============================================================================
   BUTTONS
   ============================================================================ */
.btn {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.3s;
}

.btn-primary {
    background-color: var(--primary);
    border-color: var(--primary);
}

.btn-primary:hover {
    background-color: #1e40af;
    border-color: #1e40af;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(26, 86, 219, 0.3);
}

/* ============================================================================
   FORMS
   ============================================================================ */
.form-control {
    border-radius: 8px;
    border: 2px solid var(--border-light);
    padding: 12px 20px;
    transition: all 0.3s;
}

.form-control:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 0.2rem rgba(26, 86, 219, 0.1);
}

/* ============================================================================
   FOOTER
   ============================================================================ */
.overlay-top {
    position: relative;
}

.overlay-top::before {
    content: "";
    position: absolute;
    top: -100px;
    left: 0;
    width: 100%;
    height: 100px;
    background: linear-gradient(to bottom, transparent, #343a40);
}

/* ============================================================================
   BACK TO TOP BUTTON
   ============================================================================ */
.back-to-top {
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 99;
    display: none;
}

/* ============================================================================
   ALERTS
   ============================================================================ */
.alert {
    border-radius: 8px;
    border: none;
}

/* ============================================================================
   CARDS
   ============================================================================ */
.card {
    border-radius: 12px;
    border: 1px solid var(--border-light);
    transition: all 0.3s;
}

.card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    transform: translateY(-5px);
}

/* ============================================================================
   RESPONSIVE
   ============================================================================ */
@media (max-width: 768px) {
    .navbar-brand {
        font-size: 1.2rem;
    }
    
    .btn-lg {
        padding: 12px 30px;
    }
}
'''
    
    css_path = STATIC_DIR / 'css' / 'style.css'
    try:
        print(f"  Creating style.css... ", end='', flush=True)
        css_path.write_text(css_content, encoding='utf-8')
        print(f"✓ ({len(css_content):,} bytes)")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def create_main_js():
    """Create the main.js file"""
    js_content = '''// Kolokwa Connect - Main JavaScript

(function ($) {
    "use strict";

    // Spinner
    var spinner = function () {
        setTimeout(function () {
            if ($('#spinner').length > 0) {
                $('#spinner').removeClass('show');
            }
        }, 1);
    };
    spinner();
    
    // Back to top button
    $(window).scroll(function () {
        if ($(this).scrollTop() > 300) {
            $('.back-to-top').fadeIn('slow');
        } else {
            $('.back-to-top').fadeOut('slow');
        }
    });
    
    $('.back-to-top').click(function () {
        $('html, body').animate({scrollTop: 0}, 1500, 'easeInOutExpo');
        return false;
    });

    // Smooth scrolling
    $('a[href^="#"]').on('click', function(e) {
        var target = $(this.hash);
        if (target.length) {
            e.preventDefault();
            $('html, body').animate({
                scrollTop: target.offset().top - 70
            }, 1000, 'easeInOutExpo');
        }
    });

    // Testimonials carousel (if exists)
    if ($(".testimonial-carousel").length > 0) {
        $(".testimonial-carousel").owlCarousel({
            autoplay: true,
            smartSpeed: 1000,
            items: 1,
            dots: true,
            loop: true,
            nav: false
        });
    }

    // Counter animation (if exists)
    if ($('.counter').length > 0) {
        $('.counter').counterUp({
            delay: 10,
            time: 2000
        });
    }

})(jQuery);
'''
    
    js_path = STATIC_DIR / 'js' / 'main.js'
    try:
        print(f"  Creating main.js... ", end='', flush=True)
        js_path.write_text(js_content, encoding='utf-8')
        print(f"✓ ({len(js_content):,} bytes)")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def create_logo_placeholder():
    """Create a simple SVG logo"""
    svg_content = '''<svg width="200" height="60" xmlns="http://www.w3.org/2000/svg">
  <rect width="200" height="60" fill="#1a56db" rx="8"/>
  <text x="100" y="38" font-family="Arial, sans-serif" font-size="20" fill="white" text-anchor="middle" font-weight="bold">
    KOLOKWA
  </text>
</svg>'''
    
    logo_path = STATIC_DIR / 'img' / 'logo.png'
    svg_path = STATIC_DIR / 'img' / 'logo.svg'
    
    try:
        print(f"  Creating logo.svg... ", end='', flush=True)
        svg_path.write_text(svg_content, encoding='utf-8')
        print(f"✓")
        
        # Create a placeholder PNG file
        print(f"  Creating logo.png placeholder... ", end='', flush=True)
        logo_path.write_text("Replace with actual PNG logo", encoding='utf-8')
        print(f"✓ (placeholder)")
        
        print(f"\n  📝 Note: Replace logo.png with your actual logo image")
        print(f"      You can use logo.svg temporarily by updating your template")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    if not STATIC_DIR.exists():
        print(f"\n❌ Error: Static directory not found!")
        print(f"   Expected: {STATIC_DIR}")
        return
    
    total = 0
    success = 0
    
    # Download library files
    print("\n📥 Downloading JavaScript libraries from CDN...")
    print("-" * 70)
    for file_path, url in DOWNLOADS.items():
        total += 1
        destination = STATIC_DIR / file_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if download_file(url, destination):
            success += 1
    
    # Create CSS file
    print("\n📝 Creating CSS files...")
    print("-" * 70)
    total += 1
    if create_style_css():
        success += 1
    
    # Create JS file
    print("\n📝 Creating JavaScript files...")
    print("-" * 70)
    total += 1
    if create_main_js():
        success += 1
    
    # Create logo
    print("\n🎨 Creating logo files...")
    print("-" * 70)
    total += 1
    if create_logo_placeholder():
        success += 1
    
    # Summary
    print("\n" + "=" * 70)
    print(f"Setup Complete: {success}/{total} files created successfully")
    print("=" * 70)
    
    if success == total:
        print("\n✅ All files created successfully!")
        print("\n📋 Next steps:")
        print("  1. Update settings.py with the static storage fix")
        print("  2. Run: python manage.py collectstatic --noinput --clear")
        print("  3. Run: python manage.py runserver 127.0.0.1:3000")
        print("\n📌 Optional:")
        print("  • Replace img/logo.png with your actual logo")
        print("  • Customize css/style.css as needed")
    else:
        print(f"\n⚠️  {total - success} files failed to create")
        print("Please check the errors above and try manually downloading")
    
    print("\n" + "=" * 70)

if __name__ == '__main__':
    main()