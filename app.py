from flask import Flask, render_template, request, redirect, session, url_for
import requests
import mysql.connector
from werkzeug.security import check_password_hash, generate_password_hash
import os   # ✅ added (required)

app = Flask(__name__)
app.secret_key = "supersecretkey123"

# ✅ ONLY THIS PART CHANGED (Railway MySQL)
db_config = {
    "host": os.getenv("MYSQLHOST"),
    "user": os.getenv("MYSQLUSER"),
    "password": os.getenv("MYSQLPASSWORD"),
    "database": os.getenv("MYSQLDATABASE"),
    "port": int(os.getenv("MYSQLPORT", 3306))
}

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[0], password):
            session["user"] = username
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
        if cursor.fetchone():
            conn.close()
            return render_template("signup.html", error="Username already exists")

        cursor.execute(
            "INSERT INTO users (email, username, password) VALUES (%s, %s, %s)",
            (email, username, hashed_password)
        )
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    return render_template(
        "dashboard.html",
        ai_msg="🤖 Hi! Choose a diet, ingredients or search to begin"
    )


# ---------- DIET PLAN ----------
@app.route("/diet/<diet_type>")
def diet_plan(diet_type):
    if "user" not in session:
        return redirect("/login")

    category_map = {
        "veg": "Vegetarian",
        "vegan": "Vegetarian",
        "nonveg": "Chicken",
        "weight": "Seafood"
    }

    category = category_map.get(diet_type, "Vegetarian")
    res = requests.get(
        f"https://www.themealdb.com/api/json/v1/1/filter.php?c={category}"
    )
    meals = res.json().get("meals")

    return render_template(
        "dashboard.html",
        meals=meals,
        ai_msg=f"🤖 Showing {diet_type.capitalize()} friendly meals"
    )


# ---------- SEARCH ----------
@app.route("/search", methods=["POST"])
def search():
    if "user" not in session:
        return redirect("/login")

    query = request.form["query"]
    res = requests.get(
        f"https://www.themealdb.com/api/json/v1/1/search.php?s={query}"
    )
    meals = res.json().get("meals")

    return render_template(
        "dashboard.html",
        meals=meals,
        ai_msg=f"🔍 AI found results for '{query}'"
    )


# ---------- INGREDIENT SEARCH ----------
@app.route("/ingredients", methods=["POST"])
def ingredients():
    if "user" not in session:
        return redirect("/login")

    items = [i.strip() for i in request.form["ingredients"].split(",")]
    meal_sets = []

    for item in items:
        r = requests.get(
            f"https://www.themealdb.com/api/json/v1/1/filter.php?i={item}"
        )
        data = r.json().get("meals")
        if data:
            meal_sets.append(set(m["idMeal"] for m in data))

    common_ids = set.intersection(*meal_sets) if meal_sets else set()
    meals = []

    for mid in common_ids:
        r = requests.get(
            f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={mid}"
        )
        meals.append(r.json()["meals"][0])

    return render_template(
        "dashboard.html",
        meals=meals,
        ai_msg="🧠 AI matched recipes using ingredients"
    )


# ---------- RECIPE DETAIL ----------
@app.route("/recipe/<meal_id>")
def recipe_detail(meal_id):
    if "user" not in session:
        return redirect("/login")

    res = requests.get(
        f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}"
    )
    meal = res.json()["meals"][0]

    ingredients = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}")
        meas = meal.get(f"strMeasure{i}")
        if ing and ing.strip():
            ingredients.append(f"{meas} {ing}")

    return render_template(
        "recipe_detail.html",
        meal=meal,
        ingredients=ingredients
    )


# ---------- SAVE RECIPE ----------
@app.route("/save_recipe", methods=["POST"])
def save_recipe():
    if "user" not in session:
        return redirect("/login")

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM saved_recipes WHERE username=%s AND recipe_id=%s",
        (session["user"], request.form["recipe_id"])
    )

    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO saved_recipes
            (username, recipe_id, recipe_name, recipe_url, recipe_thumb)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                session["user"],
                request.form["recipe_id"],
                request.form["recipe_name"],
                request.form["recipe_url"],
                request.form["recipe_thumb"]
            )
        )
        conn.commit()

    conn.close()
    return redirect(url_for("saved_recipes"))


# ---------- VIEW SAVED RECIPES ----------
@app.route("/saved_recipes")
def saved_recipes():
    if "user" not in session:
        return redirect("/login")

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM saved_recipes WHERE username=%s",
        (session["user"],)
    )
    saved = cursor.fetchall()
    conn.close()

    return render_template("saved_recipes.html", saved_recipes=saved)


# ---------- DELETE SAVED RECIPE ----------
@app.route("/delete_recipe", methods=["POST"])
def delete_recipe():
    if "user" not in session:
        return redirect("/login")

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM saved_recipes WHERE recipe_id=%s AND username=%s",
        (request.form["recipe_id"], session["user"])
    )

    conn.commit()
    conn.close()

    return redirect(url_for("saved_recipes"))


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ✅ ONLY THIS PART CHANGED (Railway compatible)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))