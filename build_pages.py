import os
import re
from jinja2 import Environment, FileSystemLoader

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(REPO_DIR, "templates")

env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

def build():
    print("Building static pages for GitHub Pages...")
    
    # 0. Create .nojekyll
    nojekyll_path = os.path.join(REPO_DIR, ".nojekyll")
    if not os.path.exists(nojekyll_path):
        with open(nojekyll_path, "w", encoding="utf-8") as f:
            f.write("")
        print("✓ Created .nojekyll")
    
    # 1. Render index.html
    tpl_index = env.get_template("index.html")
    html_index = tpl_index.render(
        site_name="MODEVA",
        site_hero_title="Не просто маркетплейс, a MODEVA — стиль вне времени",
        site_hero_subtitle="Ваш надёжный посредник с продавцом.",
        broadcast_message="",
        promo_code=""
    )
    
    # Adjust paths for static hosting
    html_index = html_index.replace('href="/static/', 'href="static/')
    html_index = html_index.replace('src="/static/', 'src="static/')
    html_index = html_index.replace('href="/admin"', 'href="admin.html"')
    html_index = html_index.replace('href="/"', 'href="index.html"')
    
    with open(os.path.join(REPO_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_index)
    print("✓ Created index.html")

    # 2. Render tracking.html as redirect to index.html
    tracking_redirect = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url=index.html">
    <script>window.location.href = 'index.html';</script>
    <title>Перенаправление...</title>
</head>
<body>
    <p>Перенаправление на главную страницу...</p>
</body>
</html>"""
    with open(os.path.join(REPO_DIR, "tracking.html"), "w", encoding="utf-8") as f:
        f.write(tracking_redirect)
    print("✓ Created tracking.html (redirect)")

    # 3. Render admin.html
    tpl_admin = env.get_template("admin.html")
    html_admin = tpl_admin.render(
        current_stage=1
    )
    html_admin = html_admin.replace('href="/static/', 'href="static/')
    html_admin = html_admin.replace('src="/static/', 'src="static/')
    html_admin = html_admin.replace('href="/admin"', 'href="admin.html"')
    html_admin = html_admin.replace('href="/"', 'href="index.html"')
    html_admin = html_admin.replace("window.location.href='/'", "window.location.href='index.html'")
    
    with open(os.path.join(REPO_DIR, "admin.html"), "w", encoding="utf-8") as f:
        f.write(html_admin)
    print("✓ Created admin.html")

if __name__ == "__main__":
    build()
