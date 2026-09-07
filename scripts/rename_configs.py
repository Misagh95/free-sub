#!/usr/bin/env python3
"""
Rename configs with unique female names specific to the server's country.
Includes DNS cache, DNS timeout, and geo-lookup with retry/backoff.
"""

import base64
import hashlib
import json
import re
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROTOCOL_RE = re.compile(
    r"^(vless|vmess|trojan|ss|hysteria2|tuic)://",
    re.IGNORECASE,
)

DNS_TIMEOUT = 5
GEO_TIMEOUT = 8
GEO_RETRIES = 3
GEO_BACKOFF = 1
GEO_PACE = 0.05  # small delay between lookups to stay under rate limits

_dns_cache: dict[str, str | None] = {}
_geo_cache: dict[str, tuple[str, str]] = {}  # ip -> (country_code, flag)

socket.setdefaulttimeout(DNS_TIMEOUT)

# Country code → female given names typical for that country
COUNTRY_GIRL_NAMES = {
    "US": ["Emma", "Olivia", "Ava", "Sophia", "Isabella", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn", "Abigail", "Emily", "Elizabeth", "Avery", "Ella", "Madison", "Scarlett", "Grace", "Chloe", "Lily", "Hannah", "Natalie", "Zoe", "Audrey", "Violet", "Stella", "Riley", "Paisley", "Naomi", "Penelope"],
    "NL": ["Emma", "Julia", "Mila", "Sophie", "Tess", "Anna", "Lotte", "Eva", "Sanne", "Fleur", "Noor", "Sara", "Lieke", "Femke", "Roos", "Bente", "Isa", "Saar", "Elise", "Nina", "Esmee", "Britt", "Sterre", "Anouk", "Merel", "Linde", "Maud", "Jasmijn"],
    "DE": ["Emma", "Mia", "Hannah", "Emilia", "Sophia", "Marie", "Lena", "Leonie", "Clara", "Johanna", "Frieda", "Greta", "Heidi", "Annika", "Elisa", "Amelie", "Laura", "Katharina", "Julia", "Franziska", "Petra", "Ursula", "Ingrid", "Sabine", "Monika", "Silke", "Anke", "Birgit"],
    "FR": ["Emma", "Louise", "Alice", "Chloe", "Camille", "Lea", "Manon", "Juliette", "Sarah", "Ines", "Jade", "Lina", "Anna", "Zoe", "Clara", "Margaux", "Elisa", "Amelie", "Celeste", "Margot", "Sophie", "Lucie", "Chantal", "Colette", "Anouk", "Fleur", "Mathilde", "Heloise"],
    "GB": ["Olivia", "Amelia", "Isla", "Ava", "Mia", "Ivy", "Freya", "Lily", "Florence", "Willow", "Grace", "Sophie", "Emily", "Poppy", "Charlotte", "Evelyn", "Daisy", "Phoebe", "Holly", "Jessica", "Victoria", "Elsie", "Matilda", "Rosie", "Beatrice", "Penelope", "Eleanor", "Amber"],
    "JP": ["Sakura", "Hana", "Yui", "Aoi", "Rin", "Yuna", "Haruka", "Ayaka", "Mei", "Sora", "Koharu", "Akari", "Mio", "Nanami", "Chiyo", "Emi", "Asuka", "Mizuki", "Kaori", "Natsuki", "Tomoko", "Yoko", "Aiko", "Momo", "Hinata", "Riko", "Ayame", "Fumiko"],
    "SG": ["Hui", "Ling", "Mei", "Priya", "Aisha", "Siti", "Nurul", "Cheryl", "Amanda", "Shanti", "Jasmine", "Serene", "Rachel", "Adeline", "Farah", "Xin", "Yi", "Ting", "Wen", "Siew", "Deanna", "Grace", "Sophie", "Valerie"],
    "HK": ["Mei", "Ling", "Wing", "Yan", "Yuen", "Ching", "Sze", "Ka", "Man", "Yi", "Hiu", "Wai", "Bo", "Fei", "Lan", "Suet", "Pui", "Lai", "Shan", "Yuk", "Chun", "Ming", "Hoi", "Oi"],
    "CA": ["Emma", "Olivia", "Charlotte", "Emily", "Chloe", "Sophie", "Camille", "Rose", "Alice", "Abigail", "Maya", "Ava", "Mia", "Harper", "Grace", "Leah", "Naomi", "Zoe", "Clara", "Amelie", "Juliette", "Florence", "Aurora", "Isla", "Ruby", "Chantal", "Gabrielle", "Simone"],
    "AU": ["Charlotte", "Olivia", "Ava", "Isla", "Mia", "Amelia", "Willow", "Ruby", "Grace", "Chloe", "Zoe", "Matilda", "Harper", "Evie", "Sophie", "Ivy", "Lily", "Hazel", "Violet", "Georgia", "Poppy", "Freya", "Bonnie", "Daisy", "Margot", "Tahlia", "Indigo", "Billie"],
    "IN": ["Aisha", "Priya", "Ananya", "Diya", "Riya", "Kavya", "Meera", "Saanvi", "Aarohi", "Ishita", "Lakshmi", "Pooja", "Nisha", "Shreya", "Tanvi", "Aditi", "Divya", "Ritu", "Simran", "Neha", "Anjali", "Priyanka", "Kavita", "Sunita", "Shalini", "Deepa", "Meenakshi", "Vasudha"],
    "BR": ["Maria", "Ana", "Julia", "Beatriz", "Laura", "Camila", "Gabriela", "Larissa", "Manuela", "Valentina", "Isabela", "Luiza", "Mariana", "Sofia", "Alice", "Helena", "Cecilia", "Fernanda", "Carolina", "Bruna", "Leticia", "Amanda", "Renata", "Patricia", "Livia", "Clara", "Antonia", "Vitoria"],
    "KR": ["Seo-yeon", "Ji-woo", "Ha-eun", "Min-ji", "Su-bin", "Ye-jin", "Eun-ji", "Soo-jin", "Hye-jin", "Ji-eun", "Yeon-woo", "Da-eun", "Chae-won", "Na-yeon", "Ha-rin", "Seo-jin", "Yu-na", "Bo-ra", "Hana", "Min-seo", "Ji-a", "Su-a", "Eun-seo", "Ye-rim", "Ga-eul", "Bit-na", "Sae-rom", "Do-yeon"],
    "IT": ["Sofia", "Giulia", "Aurora", "Alice", "Ginevra", "Emma", "Giorgia", "Greta", "Beatrice", "Chiara", "Francesca", "Martina", "Elena", "Silvia", "Valentina", "Alessia", "Sara", "Giada", "Ludovica", "Camilla", "Caterina", "Federica", "Eleonora", "Anna", "Isabella", "Vittoria", "Matilde", "Lucia"],
    "ES": ["Lucia", "Sofia", "Maria", "Martina", "Paula", "Julia", "Daniela", "Valeria", "Alba", "Emma", "Carla", "Elena", "Sara", "Carmen", "Nuria", "Claudia", "Irene", "Laura", "Patricia", "Rocio", "Andrea", "Noelia", "Aitana", "Candela", "Ines", "Blanca", "Eva", "Cristina"],
    "SE": ["Alice", "Maja", "Elsa", "Astrid", "Freja", "Wilma", "Saga", "Ebba", "Lovisa", "Agnes", "Ingrid", "Signe", "Linnea", "Selma", "Clara", "Ellen", "Greta", "Vera", "Elin", "Alma", "Lilly", "Molly", "Nora", "Iris", "Tilde", "Alicia", "Stina", "Rut"],
    "NO": ["Nora", "Emma", "Ella", "Emilie", "Ingrid", "Astrid", "Sigrid", "Freya", "Maja", "Oda", "Solveig", "Ingeborg", "Liv", "Hilde", "Ida", "Anna", "Sofia", "Jenny", "Hedda", "Thea", "Amalie", "Vilde", "Mathilde", "Kari", "Ragnhild", "Maren", "Tuva", "Sunniva"],
    "FI": ["Aino", "Emma", "Helmi", "Venla", "Sofia", "Aada", "Olivia", "Linnea", "Siiri", "Iida", "Elsa", "Inkeri", "Maija", "Anneli", "Riitta", "Paivi", "Sari", "Katja", "Minna", "Johanna", "Laura", "Heidi", "Eeva", "Tuula", "Kaarina", "Sinikka", "Marja", "Helena"],
    "PL": ["Zuzanna", "Julia", "Maja", "Hanna", "Aleksandra", "Natalia", "Wiktoria", "Oliwia", "Zofia", "Lena", "Alicja", "Maria", "Kinga", "Karolina", "Magdalena", "Agnieszka", "Katarzyna", "Ewa", "Barbara", "Anna", "Dorota", "Joanna", "Monika", "Paulina", "Weronika", "Emilia", "Iga", "Nadia"],
    "TR": ["Elif", "Zeynep", "Defne", "Asel", "Eylul", "Alya", "Zehra", "Meryem", "Ayse", "Fatma", "Busra", "Esra", "Selin", "Deniz", "Irem", "Elanur", "Dilara", "Sude", "Melis", "Ceylin", "Asya", "Nehir", "Ecrin", "Ikra", "Miray", "Zumra", "Azra", "Nil"],
    "AE": ["Fatima", "Ayesha", "Mariam", "Noor", "Salma", "Zainab", "Hessa", "Amna", "Latifa", "Shaikha", "Meera", "Alia", "Sara", "Dana", "Maitha", "Moza", "Shamma", "Hind", "Afra", "Munira", "Alya", "Reem", "Noura", "Maha"],
    "ZA": ["Zanele", "Thandiwe", "Nomvula", "Lerato", "Naledi", "Busisiwe", "Khanyisile", "Ayanda", "Palesa", "Mpumi", "Lungile", "Siphiwe", "Nokuthula", "Thandeka", "Zinhle", "Amahle", "Lindiwe", "Boitumelo", "Tshegofatso", "Kgosi", "Refilwe", "Karabo", "Dimpho", "Tumi"],
    "MX": ["Sofia", "Valentina", "Regina", "Maria", "Ximena", "Camila", "Valeria", "Renata", "Fernanda", "Daniela", "Alejandra", "Lupita", "Frida", "Paloma", "Guadalupe", "Ana", "Mariana", "Jimena", "Andrea", "Victoria", "Lucia", "Emilia", "Catalina", "Montserrat", "Itzel", "Ximena", "Paulina", "Claudia"],
    "CH": ["Emma", "Mia", "Lena", "Lia", "Nora", "Anna", "Sofia", "Alina", "Julia", "Chiara", "Giulia", "Noemi", "Elin", "Amelie", "Lara", "Elena", "Sina", "Laura", "Selina", "Nadia", "Vivienne", "Eliane", "Corinne", "Ursula", "Heidi", "Annina", "Salome", "Rahel"],
    "RU": ["Anastasia", "Maria", "Olga", "Svetlana", "Tatiana", "Natalia", "Ekaterina", "Irina", "Elena", "Daria", "Anna", "Yulia", "Vera", "Polina", "Ksenia", "Alina", "Dina", "Galina", "Ludmila", "Nadezhda", "Oksana", "Raisa", "Tamara", "Valentina", "Zoya", "Varvara", "Milana", "Arina"],
    "UA": ["Oksana", "Olena", "Kateryna", "Yulia", "Iryna", "Natalia", "Svitlana", "Olya", "Hanna", "Tetiana", "Mariya", "Anna", "Viktoria", "Solomiya", "Ivanna", "Daryna", "Zoryana", "Halyna", "Lesya", "Nadiya", "Larysa", "Ruslana", "Yaroslava", "Khrystyna", "Valeriya", "Bohdana", "Oleksandra", "Alina"],
    "IR": ["Fatemeh", "Zahra", "Maryam", "Sara", "Niloofar", "Yasmin", "Elham", "Leila", "Parisa", "Shirin", "Mina", "Nazanin", "Azar", "Bahar", "Golnaz", "Roya", "Sima", "Tara", "Vida", "Mahsa", "Setareh", "Negar", "Shabnam", "Golshifteh", "Anahita", "Donya", "Hanieh", "Melika"],
    "ID": ["Siti", "Dewi", "Putri", "Ayu", "Sri", "Rina", "Intan", "Kartika", "Nurul", "Lestari", "Indah", "Ratna", "Wulan", "Melati", "Citra", "Maya", "Sekar", "Anisa", "Fitri", "Aisyah", "Laila", "Mira", "Zahra", "Tania"],
    "MY": ["Siti", "Nurul", "Aisyah", "Farah", "Mei", "Priya", "Kavitha", "Syafiqah", "Amira", "Zara", "Hannah", "Sarah", "Nadia", "Izzah", "Adibah", "Sharmila", "Devi", "Intan", "Marina", "Sofea", "Balqis", "Hana", "Aina", "Nisa"],
    "TH": ["Suda", "Malai", "Nok", "Pranee", "Siriporn", "Chanya", "Panida", "Duangjai", "Kannika", "Naree", "Rung", "Wilai", "Anchalee", "Busaba", "Chompoo", "Dao", "Fah", "Jintana", "Kulap", "Lamai", "Malee", "Nuan", "Somsri", "Vilai"],
    "VN": ["Linh", "Lan", "Mai", "Hoa", "Huong", "Trang", "Thao", "Ngoc", "Anh", "Phuong", "Van", "Hanh", "Thu", "Ha", "Chi", "Nga", "Bich", "Dao", "Minh", "Tuyet", "Kieu", "Loan", "My", "Nhung"],
    "PH": ["Maria", "Ana", "Kristine", "Angel", "Grace", "Faith", "Princess", "Joy", "Liza", "Marites", "Luzviminda", "Imelda", "Corazon", "Juanita", "Rosario", "Mariposa", "Liwayway", "Amihan", "Tala", "Malaya", "Diwata", "Bituin", "Luningning", "Ilang"],
    "TW": ["Mei-ling", "Shu-fen", "Ya-wen", "Hsin-yi", "Chia-ling", "Pei-ju", "Yu-hsin", "Ling", "Hui", "Chen", "Li-hua", "Su-yin", "Ai-ling", "Fen", "Jie", "Ming-hui", "Shu-hui", "Hsiu-lan", "I-chun", "Wen-jing", "Chun-mei", "Yuan", "Chi", "Yun"],
    "IL": ["Noa", "Tamar", "Yael", "Shira", "Maya", "Michal", "Hila", "Rotem", "Adi", "Talia", "Rachel", "Sara", "Aviva", "Dalia", "Shoshana", "Tali", "Noga", "Efrat", "Rivka", "Yael", "Naomi", "Hadar", "Lior", "Ofra"],
    "SA": ["Noura", "Sara", "Rania", "Lamia", "Aisha", "Huda", "Reem", "Dana", "Arwa", "Lujain", "Mashael", "Maha", "Joud", "Rima", "Ghada", "Abeer", "Hessa", "Fawzia", "Hanan", "Manal", "Shatha", "Tala", "Aljohara", "Bashaer"],
    "EG": ["Fatima", "Mariam", "Nour", "Salma", "Aya", "Hana", "Laila", "Yasmin", "Malak", "Farida", "Habiba", "Omnia", "Nada", "Mona", "Sama", "Rana", "Heba", "Amira", "Doaa", "Shaimaa", "Esraa", "Mennatallah", "Rowan", "Jana"],
    "NG": ["Amina", "Fatima", "Zainab", "Ngozi", "Chioma", "Adaeze", "Nneka", "Ifeoma", "Chiamaka", "Blessing", "Precious", "Uche", "Amaka", "Chidinma", "Funke", "Ijeoma", "Nkechi", "Obiageli", "Yewande", "Temitope", "Abimbola", "Folake", "Kehinde", "Adanna"],
    "KE": ["Wanjiku", "Akinyi", "Njeri", "Atieno", "Muthoni", "Wambui", "Achieng", "Chebet", "Kendi", "Naliaka", "Nyambura", "Wairimu", "Makena", "Nekesa", "Adhiambo", "Anyango", "Kemunto", "Moraa", "Chepkoech", "Jendela", "Naserian", "Salome", "Nafula", "Awino"],
    "AR": ["Sofia", "Valentina", "Martina", "Catalina", "Julieta", "Camila", "Morena", "Agostina", "Milagros", "Lucia", "Emilia", "Victoria", "Bianca", "Mora", "Juana", "Paloma", "Renata", "Delfina", "Isabella", "Amparo", "Pilar", "Candelaria", "Malena", "Antonia"],
    "CL": ["Sofia", "Martina", "Florencia", "Javiera", "Isidora", "Antonia", "Fernanda", "Valentina", "Emilia", "Catalina", "Josefa", "Trinidad", "Amanda", "Constanza", "Victoria", "Agustina", "Ignacia", "Gabriela", "Paula", "Magdalena", "Elisa", "Francisca", "Renata", "Colomba"],
    "CO": ["Maria", "Valentina", "Isabella", "Camila", "Sara", "Gabriela", "Daniela", "Laura", "Valeria", "Juliana", "Manuela", "Mariana", "Salome", "Luciana", "Natalia", "Carolina", "Ximena", "Ana", "Sofia", "Alejandra", "Isabela", "Antonia", "Emilia", "Lucia"],
    "PE": ["Maria", "Sofia", "Valentina", "Camila", "Luciana", "Brianna", "Aitana", "Ariana", "Danna", "Fabiana", "Xiomara", "Fatima", "Mia", "Naomi", "Salome", "Antonella", "Guadalupe", "Micaela", "Milagros", "Renata", "Mariel", "Kori", "Suyana", "Lluvia"],
    "PT": ["Maria", "Beatriz", "Leonor", "Matilde", "Carolina", "Mariana", "Ines", "Francisca", "Margarida", "Sofia", "Ana", "Joana", "Rita", "Clara", "Madalena", "Constanca", "Benedita", "Mafalda", "Teresa", "Catarina", "Sara", "Laura", "Eva", "Raquel"],
    "GR": ["Maria", "Eleni", "Katerina", "Sofia", "Despina", "Georgia", "Ioanna", "Alexandra", "Vasiliki", "Christina", "Panagiota", "Anastasia", "Fotini", "Evangelia", "Konstantina", "Dimitra", "Efthymia", "Theodora", "Nikoletta", "Stavroula", "Angeliki", "Paraskevi", "Aikaterini", "Zoi"],
    "CZ": ["Eliska", "Tereza", "Anna", "Adela", "Karolina", "Natalie", "Kristyna", "Lucie", "Veronika", "Barbora", "Eva", "Petra", "Jana", "Hana", "Lenka", "Marketa", "Michaela", "Pavla", "Renata", "Simona", "Klara", "Terezie", "Julie", "Sofie"],
    "AT": ["Anna", "Emma", "Mia", "Lena", "Sophie", "Marie", "Johanna", "Katharina", "Julia", "Lisa", "Laura", "Teresa", "Amelie", "Hannah", "Valentina", "Elena", "Nina", "Clara", "Isabella", "Marlene", "Leonie", "Sarah", "Melanie", "Elisabeth"],
    "BE": ["Emma", "Louise", "Olivia", "Alice", "Juliette", "Marie", "Elise", "Camille", "Charlotte", "Nora", "Anna", "Lotte", "Fien", "Lise", "Manon", "Margaux", "Ines", "Leonie", "Amelie", "Jeanne", "Maya", "Eva", "Amber", "Eline"],
    "DK": ["Emma", "Freja", "Ida", "Clara", "Laura", "Sofia", "Astrid", "Signe", "Mathilde", "Camilla", "Mette", "Hanne", "Lene", "Bente", "Birgit", "Inge", "Karin", "Rikke", "Sanne", "Maja", "Alma", "Agnes", "Liva", "Nora"],
    "RO": ["Maria", "Elena", "Ioana", "Andreea", "Alexandra", "Gabriela", "Cristina", "Ana", "Daria", "Bianca", "Mihaela", "Simona", "Camelia", "Alina", "Georgiana", "Ramona", "Doina", "Flavia", "Corina", "Daniela", "Ioana", "Iulia", "Teodora", "Raluca"],
    "BG": ["Maria", "Elena", "Iva", "Nadezhda", "Yana", "Ralitsa", "Gergana", "Svetlana", "Milena", "Desislava", "Petya", "Vanya", "Tsvetelina", "Ivanka", "Margarita", "Silvia", "Vesela", "Kamelia", "Radka", "Ani", "Eli", "Bilyana", "Dobrinka", "Rumyana"],
    "HU": ["Anna", "Hanna", "Zsofia", "Lili", "Emma", "Luca", "Boglarka", "Fanni", "Lilla", "Eszter", "Judit", "Eva", "Katalin", "Zsuzsanna", "Ilona", "Edit", "Agnes", "Klaudia", "Reka", "Noemi", "Vivien", "Dorina", "Szofia", "Petra"],
    "IE": ["Aoife", "Ciara", "Niamh", "Saoirse", "Siobhan", "Grainne", "Aisling", "Eabha", "Roisin", "Orla", "Maeve", "Deirdre", "Sinead", "Bronagh", "Caoimhe", "Clodagh", "Fionnuala", "Imelda", "Kathleen", "Mary", "Erin", "Riona", "Bridget", "Nuala"],
    "NZ": ["Charlotte", "Olivia", "Isla", "Ava", "Mia", "Harper", "Ruby", "Willow", "Grace", "Sophie", "Lily", "Eva", "Amelia", "Chloe", "Georgia", "Poppy", "Hazel", "Ivy", "Freya", "Matilda", "Maia", "Aroha", "Whetu", "Moana"],
}

DEFAULT_GIRL_NAMES = ["Ava", "Bella", "Chloe", "Daisy", "Elena", "Freya", "Grace", "Hazel", "Ivy", "Jade", "Kira", "Luna", "Mila", "Nina", "Olivia", "Poppy", "Quinn", "Ruby", "Sofia", "Tara", "Uma", "Vera", "Willow", "Yara", "Zoe", "Aria", "Nova", "Iris"]

def country_flag(country_code: str) -> str:
    cc = (country_code or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in cc)


def _stable_number(seed: str, modulo: int) -> int:
    """Deterministic 0..modulo-1 number derived from a server identity."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % modulo


def generate_name(country_code: str, seed: str) -> str:
    """Deterministic female name for a config, specific to the country.

    Both the name and the number are derived from the server identity (the
    full base URI), so the same server always keeps the same name across
    runs and duplicate servers collapse into a single entry.
    """
    cc = (country_code or "").upper()
    names = COUNTRY_GIRL_NAMES.get(cc, DEFAULT_GIRL_NAMES)
    word = names[_stable_number(seed, len(names))]
    number = _stable_number(seed, 999) + 1
    return f"{word}-{number}"


def extract_host(line: str) -> str | None:
    base = line.split("#", 1)[0].strip()
    try:
        parsed = urllib.parse.urlsplit(base)
        if parsed.hostname:
            return parsed.hostname.strip("[]")
    except Exception:
        pass
    match = re.search(r"@([^:/?#]+)", base)
    return match.group(1) if match else None


def resolve_ip(host: str | None) -> str | None:
    if not host:
        return None
    if host in _dns_cache:
        return _dns_cache[host]
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        _dns_cache[host] = host
        return host
    try:
        ip = socket.gethostbyname(host)
        _dns_cache[host] = ip
        return ip
    except Exception:
        _dns_cache[host] = None
        return None


def get_country_info(ip: str | None) -> tuple[str, str]:
    """Return (country_code, flag) for an IP."""
    if not ip:
        return ("", "🌐")
    if ip in _geo_cache:
        return _geo_cache[ip]

    for attempt in range(GEO_RETRIES + 1):
        try:
            time.sleep(GEO_PACE * (attempt + 1))
            req = urllib.request.Request(
                f"https://ipwho.is/{urllib.parse.quote(ip)}",
                headers={"User-Agent": "DGDreams-Config-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=GEO_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cc = (data.get("country_code") or "").upper()
            flag = country_flag(cc)
            _geo_cache[ip] = (cc, flag)
            return (cc, flag)
        except Exception:
            if attempt < GEO_RETRIES:
                time.sleep(GEO_BACKOFF * (attempt + 1))

    _geo_cache[ip] = ("", "🌐")
    return ("", "🌐")


def rename_config(line: str) -> str | None:
    """Rename a config with a unique random country-based name."""
    line = line.strip()
    if not PROTOCOL_RE.match(line):
        return None

    base = line.split("#", 1)[0].strip()
    host = extract_host(base)
    ip = resolve_ip(host)
    cc, flag = get_country_info(ip)
    name = generate_name(cc, base)

    return f"{base}#{flag} {name}"


def main(
    raw_path: str = "/tmp/raw_configs.txt",
    out_txt: str = "configs.txt",
    out_b64: str = "configs_base64.txt",
):
    raw_text = Path(raw_path).read_text(encoding="utf-8", errors="ignore")

    configs: set[str] = set()
    for line in raw_text.splitlines():
        renamed = rename_config(line)
        if renamed:
            configs.add(renamed)

    configs_sorted = sorted(configs)
    output = ("\n".join(configs_sorted) + "\n") if configs_sorted else ""

    Path(out_txt).write_text(output, encoding="utf-8")
    Path(out_b64).write_text(
        base64.b64encode(output.encode("utf-8")).decode("ascii"),
        encoding="utf-8",
    )
    print(f"Final configs: {len(configs_sorted)}")

    # print sample names
    for c in configs_sorted[:5]:
        name = c.split("#", 1)[1] if "#" in c else c
        print(f"  {name}")


if __name__ == "__main__":
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else "/tmp/raw_configs.txt"
    txt = sys.argv[2] if len(sys.argv) > 2 else "configs.txt"
    b64 = sys.argv[3] if len(sys.argv) > 3 else "configs_base64.txt"
    main(raw, txt, b64)
