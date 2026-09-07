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

# Country code -> female names + famous landmarks/cultural references + famous women
COUNTRY_GIRL_NAMES = {
    # United States
    "US": [
        # Female names
        "Emma", "Olivia", "Ava", "Sophia", "Isabella", "Mia", "Charlotte", "Amelia",
        "Harper", "Evelyn", "Abigail", "Emily", "Elizabeth", "Avery", "Ella",
        "Madison", "Scarlett", "Grace", "Chloe", "Lily", "Hannah", "Natalie",
        "Zoe", "Audrey", "Violet", "Stella", "Riley", "Paisley", "Naomi", "Penelope",
        # Landmarks & culture
        "Liberty", "Hollywood", "Statue", "Brooklyn", "Manhattan", "California",
        "Savannah", "Phoenix", "Sierra", "Dakota", "Virginia", "Georgia",
        "Madison", "Chelsea", "Brooklyn", "Harper", "Parker", "Kennedy",
        # Famous women
        "Eleanor", "Amelia", "Marie", "Rosa", "Helen", "Florence", "Clara",
        "Harriet", "Sacagawea", "Sally", "Maya", "Toni", "Sonia", "Ruth",
    ],
    # Netherlands
    "NL": [
        # Female names
        "Emma", "Julia", "Mila", "Sophie", "Tess", "Anna", "Lotte", "Eva",
        "Sanne", "Fleur", "Noor", "Sara", "Lieke", "Femke", "Roos", "Bente",
        "Isa", "Saar", "Elise", "Nina", "Esmee", "Britt", "Sterre", "Anouk",
        "Merel", "Linde", "Maud", "Jasmijn",
        # Landmarks & culture
        "Amsterdam", "Tulip", "Windmill", "Canal", "Zaanse", "Keukenhof",
        "Anne", "Rembrandt", "Vermeer", "VanGogh", "Stroopwafel", "Gouda",
        # Famous women
        "Anne", "Corrie", "Matilda", "Aletta", "Fanny", "Kate", "Fiep",
    ],
    # Germany
    "DE": [
        # Female names
        "Emma", "Mia", "Hannah", "Emilia", "Sophia", "Marie", "Lena", "Leonie",
        "Clara", "Johanna", "Frieda", "Greta", "Heidi", "Annika", "Elisa", "Amelie",
        "Laura", "Katharina", "Julia", "Franziska", "Petra", "Ursula", "Ingrid",
        "Sabine", "Monika", "Silke", "Anke", "Birgit",
        # Landmarks & culture
        "Berlin", "Munich", "Hamburg", "Bavaria", "Rhine", "BlackForest",
        "Brandenburg", "Oktoberfest", "Neuschwanstein", "Schwarzwald",
        # Famous women
        "Angela", "Merkel", "Marlene", "Dietrich", "Hannah", "Arendt",
        "Sophie", "Scholl", "Emmy", "Noether", "Ada", "Lovelace",
    ],
    # France
    "FR": [
        # Female names
        "Emma", "Louise", "Alice", "Chloe", "Camille", "Lea", "Manon", "Juliette",
        "Sarah", "Ines", "Jade", "Lina", "Anna", "Zoe", "Clara", "Margaux",
        "Elisa", "Amelie", "Celeste", "Margot", "Sophie", "Lucie", "Chantal",
        "Colette", "Anouk", "Fleur", "Mathilde", "Heloise",
        # Landmarks & culture
        "Eiffel", "Louvre", "Montmartre", "Versailles", "Bordeaux", "Champagne",
        "Bastille", "Riviera", "Provence", "Alsace", "Normandy", "Paris",
        # Famous women
        "Marie", "Curie", "Coco", "Chanel", "Brigitte", "Bardot",
        "Simone", "Beauvoir", "Edith", "Piaf", "Josephine", "Baker",
    ],
    # United Kingdom
    "GB": [
        # Female names
        "Olivia", "Amelia", "Isla", "Ava", "Mia", "Ivy", "Freya", "Lily",
        "Florence", "Willow", "Grace", "Sophie", "Emily", "Poppy", "Charlotte",
        "Evelyn", "Daisy", "Phoebe", "Holly", "Jessica", "Victoria", "Elsie",
        "Matilda", "Rosie", "Beatrice", "Penelope", "Eleanor", "Amber",
        # Landmarks & culture
        "London", "Thames", "Cambridge", "Oxford", "Edinburgh", "York",
        "Windsor", "Stonehenge", "BigBen", "Hyde", "Park", "Westminster",
        # Famous women
        "Queen", "Elizabeth", "Victoria", "Mary", "Curie", "Austen",
        "Bronte", "Rowling", "Galton", "Pankhurst", "Nightingale",
    ],
    # Japan
    "JP": [
        # Female names
        "Sakura", "Hana", "Yui", "Aoi", "Rin", "Yuna", "Haruka", "Ayaka",
        "Mei", "Sora", "Koharu", "Akari", "Mio", "Nanami", "Chiyo", "Emi",
        "Asuka", "Mizuki", "Kaori", "Natsuki", "Tomoko", "Yoko", "Aiko", "Momo",
        "Hinata", "Riko", "Ayame", "Fumiko",
        # Landmarks & culture
        "Fuji", "Sakura", "Cherry", "Blossom", "Geisha", "Samurai", "Zen",
        "Torii", "Shibuya", "Harajuku", "Osaka", "Kyoto", "Nara", "Hokkaido",
        # Famous women
        "Akiko", "Yosano", "Murasaki", "Shikibu", "Hatsune", "Miku",
        "Naoko", "Takei", "Fumiko", "Hayashi", "Matsuo", "Basho",
    ],
    # Singapore
    "SG": [
        # Female names
        "Hui", "Ling", "Mei", "Priya", "Aisha", "Siti", "Nurul", "Cheryl",
        "Amanda", "Shanti", "Jasmine", "Serene", "Rachel", "Adeline", "Farah",
        "Xin", "Yi", "Ting", "Wen", "Siew", "Deanna", "Grace", "Sophie", "Valerie",
        # Landmarks & culture
        "Merlion", "Orchid", "Marina", "Sentosa", "Changi", "Raffles",
        "Gardens", "Bay", "Kampong", "Tiong", "Bharu", "Toa",
        # Famous women
        "Stella", "Tan", "Lim", "Geok", "Choo", "Wei", "Ling",
    ],
    # Hong Kong
    "HK": [
        # Female names
        "Mei", "Ling", "Wing", "Yan", "Yuen", "Ching", "Sze", "Ka",
        "Man", "Yi", "Hiu", "Wai", "Bo", "Fei", "Lan", "Suet",
        "Pui", "Lai", "Shan", "Yuk", "Chun", "Ming", "Hoi", "Oi",
        # Landmarks & culture
        "Victoria", "Peak", "Star", "Ferry", "Harbour", "Temple",
        "Night", "Market", "Dim", "Sum", "Kowloon", "Island",
        # Famous women
        "Michele", "Reis", "Anita", "Mui", "Carina", "Lau",
    ],
    # Canada
    "CA": [
        # Female names
        "Emma", "Olivia", "Charlotte", "Emily", "Chloe", "Sophie", "Camille",
        "Rose", "Alice", "Abigail", "Maya", "Ava", "Mia", "Harper", "Grace",
        "Leah", "Naomi", "Zoe", "Clara", "Amelie", "Juliette", "Florence",
        "Aurora", "Isla", "Ruby", "Chantal", "Gabrielle", "Simone",
        # Landmarks & culture
        "Maple", "Rocky", "Ontario", "Quebec", "Banff", "Niagara",
        "Vancouver", "Toronto", "Ottawa", "Prairie", "Tundra", "Aurora",
        # Famous women
        "Margaret", "Atwood", "Celine", "Dion", "Sandra", "Oh",
        "Mary", "Pickford", "Lucy", "Maud", "Montgomery",
    ],
    # Australia
    "AU": [
        # Female names
        "Charlotte", "Olivia", "Ava", "Isla", "Mia", "Amelia", "Willow", "Ruby",
        "Grace", "Chloe", "Zoe", "Matilda", "Harper", "Evie", "Sophie", "Ivy",
        "Lily", "Hazel", "Violet", "Georgia", "Poppy", "Freya", "Bonnie", "Daisy",
        "Margot", "Tahlia", "Indigo", "Billie",
        # Landmarks & culture
        "Sydney", "Opera", "Reef", "Outback", "Koala", "Kangaroo",
        "Uluru", "Bondi", "Melbourne", "Brisbane", "Perth", "Adelaide",
        # Famous women
        "Cate", "Blanchett", "Nicole", "Kidman", "Julia", "Gillard",
        "Dame", "Edna", "Nellie", "Melba",
    ],
    # India
    "IN": [
        # Female names
        "Aisha", "Priya", "Ananya", "Diya", "Riya", "Kavya", "Meera", "Saanvi",
        "Aarohi", "Ishita", "Lakshmi", "Pooja", "Nisha", "Shreya", "Tanvi",
        "Aditi", "Divya", "Ritu", "Simran", "Neha", "Anjali", "Priyanka",
        "Kavita", "Sunita", "Shalini", "Deepa", "Meenakshi", "Vasudha",
        # Landmarks & culture
        "Taj", "Mahal", "Lotus", "Ganges", "Delhi", "Mumbai", "Spice",
        "Saffron", "Indus", "Himalaya", "Goa", "Kerala", "Rajasthan",
        # Famous women
        "Indira", "Gandhi", "Mother", "Teresa", "Sarojini", "Naidu",
        "Kalpana", "Chawla", "Aishwarya", "Rai",
    ],
    # Brazil
    "BR": [
        # Female names
        "Maria", "Ana", "Julia", "Beatriz", "Laura", "Camila", "Gabriela",
        "Larissa", "Manuela", "Valentina", "Isabela", "Luiza", "Mariana",
        "Sofia", "Alice", "Helena", "Cecilia", "Fernanda", "Carolina", "Bruna",
        "Leticia", "Amanda", "Renata", "Patricia", "Livia", "Clara", "Antonia", "Vitoria",
        # Landmarks & culture
        "Amazon", "Rio", "Carnival", "Tropical", "Samba", "Copa",
        "Verde", "Sol", "Ipanema", "Copacabana", "Corcovado", "Sugarloaf",
        # Famous women
        "Frida", "Kahlo", "Sonia", "Braga", "Gisele", "Bundchen",
        "Adriana", "Lima", "Susana", "Werner",
    ],
    # South Korea
    "KR": [
        # Female names
        "Seo-yeon", "Ji-woo", "Ha-eun", "Min-ji", "Su-bin", "Ye-jin",
        "Eun-ji", "Soo-jin", "Hye-jin", "Ji-eun", "Yeon-woo", "Da-eun",
        "Chae-won", "Na-yeon", "Ha-rin", "Seo-jin", "Yu-na", "Bo-ra",
        "Hana", "Min-seo", "Ji-a", "Su-a", "Eun-seo", "Ye-rim",
        "Ga-eul", "Bit-na", "Sae-rom", "Do-yeon",
        # Landmarks & culture
        "Seoul", "Han", "Gangnam", "Jeju", "Gyeongbok", "Bukchon",
        "Namsan", "Myeongdong", "Insadong", "Itaewon", "K-Star", "K-Pop",
        # Famous women
        "Yoona", "Taeyeon", "IU", "Bae", "Suzy", "Gong", "Yoo",
    ],
    # Italy
    "IT": [
        # Female names
        "Sofia", "Giulia", "Aurora", "Alice", "Ginevra", "Emma", "Giorgia",
        "Greta", "Beatrice", "Chiara", "Francesca", "Martina", "Elena",
        "Silvia", "Valentina", "Alessia", "Sara", "Giada", "Ludovica", "Camilla",
        "Caterina", "Federica", "Eleonora", "Anna", "Isabella", "Vittoria",
        "Matilde", "Lucia",
        # Landmarks & culture
        "Roma", "Milan", "Venice", "Florence", "Tuscany", "Amalfi",
        "Colosseum", "Vatican", "Pisa", "Como", "Capri", "Siena",
        # Famous women
        "Sophia", "Loren", "Monica", "Bellucci", "Valentina", "Cortese",
        "Gina", "Lollobrigida",
    ],
    # Spain
    "ES": [
        # Female names
        "Lucia", "Sofia", "Maria", "Martina", "Paula", "Julia", "Daniela",
        "Valeria", "Alba", "Emma", "Carla", "Elena", "Sara", "Carmen",
        "Nuria", "Claudia", "Irene", "Laura", "Patricia", "Rocio", "Andrea",
        "Noelia", "Aitana", "Candela", "Ines", "Blanca", "Eva", "Cristina",
        # Landmarks & culture
        "Madrid", "Barcelona", "Flamenco", "Sagrada", "Familia", "Alhambra",
        "Costa", "Brava", "Iberia", "Cobre", "Sol", "Torero",
        # Famous women
        "Penelope", "Cruz", "Salma", "Hayek", "Antonio", "Banderas",
        "Pablo", "Picasso", "Frida", "Kahlo",
    ],
    # Sweden
    "SE": [
        # Female names
        "Alice", "Maja", "Elsa", "Astrid", "Freja", "Wilma", "Saga", "Ebba",
        "Lovisa", "Agnes", "Ingrid", "Signe", "Linnea", "Selma", "Clara",
        "Ellen", "Greta", "Vera", "Elin", "Alma", "Lilly", "Molly", "Nora",
        "Iris", "Tilde", "Alicia", "Stina", "Rut",
        # Landmarks & culture
        "Stockholm", "Gothenburg", "Malmö", "Viking", "Fjord", "Aurora",
        "Nordic", "Frost", "Elk", "Saga", "Midsummer", "IKEA",
        # Famous women
        "Greta", "Garbo", "Ingrid", "Bergman", "Astrid", "Lindgren",
        "ABBA", "Agatha", "Christie",
    ],
    # Norway
    "NO": [
        # Female names
        "Nora", "Emma", "Ella", "Emilie", "Ingrid", "Astrid", "Sigrid", "Freya",
        "Maja", "Oda", "Solveig", "Ingeborg", "Liv", "Hilde", "Ida", "Anna",
        "Sofia", "Jenny", "Hedda", "Thea", "Amalie", "Vilde", "Mathilde",
        "Kari", "Ragnhild", "Maren", "Tuva", "Sunniva",
        # Landmarks & culture
        "Oslo", "Bergen", "Tromsø", "Fjord", "Viking", "Aurora",
        "Nordic", "Storm", "Glacier", "Bjorn", "Stave", "Church",
        # Famous women
        "Fridtjof", "Nansen", "Edvard", "Munch", "Henrik", "Ibsen",
        "Sofie", "Amalie",
    ],
    # Finland
    "FI": [
        # Female names
        "Aino", "Emma", "Helmi", "Venla", "Sofia", "Aada", "Olivia", "Linnea",
        "Siiri", "Iida", "Elsa", "Inkeri", "Maija", "Anneli", "Riitta", "Paivi",
        "Sari", "Katja", "Minna", "Johanna", "Laura", "Heidi", "Eeva", "Tuula",
        "Kaarina", "Sinikka", "Marja", "Helena",
        # Landmarks & culture
        "Helsinki", "Sauna", "Snow", "Fox", "Frost", "Birch", "Lumi", "Suomi",
        "Northern", "Lights", "Lakes", "Forest", "Midnight", "Sun",
        # Famous women
        "Jean", "Sibelius", "Tove", "Jansson", "Moomin",
    ],
    # Poland
    "PL": [
        # Female names
        "Zuzanna", "Julia", "Maja", "Hanna", "Aleksandra", "Natalia", "Wiktoria",
        "Oliwia", "Zofia", "Lena", "Alicja", "Maria", "Kinga", "Karolina",
        "Magdalena", "Agnieszka", "Katarzyna", "Ewa", "Barbara", "Anna",
        "Dorota", "Joanna", "Monika", "Paulina", "Weronika", "Emilia", "Iga", "Nadia",
        # Landmarks & culture
        "Warsaw", "Krakow", "Bison", "Amber", "Vistula", "Pioneer", "Forge", "Shield",
        "Auschwitz", "Solidarity", "Chopin", "Pierogi",
        # Famous women
        "Marie", "Curie", "Wisla", "Szymborska", "Agnieszka", "Holland",
    ],
    # Turkey
    "TR": [
        # Female names
        "Elif", "Zeynep", "Defne", "Asel", "Eylul", "Alya", "Zehra", "Meryem",
        "Ayse", "Fatma", "Busra", "Esra", "Selin", "Deniz", "Irem", "Elanur",
        "Dilara", "Sude", "Melis", "Ceylin", "Asya", "Nehir", "Ecrin", "Ikra",
        "Miray", "Zumra", "Azra", "Nil",
        # Landmarks & culture
        "Istanbul", "Bosphorus", "Crescent", "Anatolia", "Sultan", "Spice",
        "Silk", "Odin", "Hagia", "Sophia", "Blue", "Mosque", "Cappadocia",
        # Famous women
        "Hurrem", "Sultan", "Turkan", "Soray", "Filiz", "Akin",
    ],
    # UAE
    "AE": [
        # Female names
        "Fatima", "Ayesha", "Mariam", "Noor", "Salma", "Zainab", "Hessa",
        "Amna", "Latifa", "Shaikha", "Meera", "Alia", "Sara", "Dana",
        "Maitha", "Moza", "Shamma", "Hind", "Afra", "Munira", "Alya",
        "Reem", "Noura", "Maha",
        # Landmarks & culture
        "Dubai", "Oasis", "Falcon", "Sand", "Gold", "Pearl", "Desert", "Sahara",
        "Burj", "Khalifa", "Palm", "Jumeirah", "Abu", "Dhabi",
        # Famous women
        "Mozha", "Al", "Maktoum", "Hessa", "Al", "Jaber",
    ],
    # South Africa
    "ZA": [
        # Female names
        "Zanele", "Thandiwe", "Nomvula", "Lerato", "Naledi", "Busisiwe",
        "Khanyisile", "Ayanda", "Palesa", "Mpumi", "Lungile", "Siphiwe",
        "Nokuthula", "Thandeka", "Zinhle", "Amahle", "Lindiwe", "Boitumelo",
        "Tshegofatso", "Kgosi", "Refilwe", "Karabo", "Dimpho", "Tumi",
        # Landmarks & culture
        "Cape", "Diamond", "Safari", "Lion", "Ubuntu", "Thorn", "Kruger", "Sun",
        "Table", "Mountain", "Garden", "Route", "Drakensberg",
        # Famous women
        "Miriam", "Makeba", "Desmond", "Tutu", "Nelson", "Mandela",
    ],
    # Mexico
    "MX": [
        # Female names
        "Sofia", "Valentina", "Regina", "Maria", "Ximena", "Camila", "Valeria",
        "Renata", "Fernanda", "Daniela", "Alejandra", "Lupita", "Frida",
        "Paloma", "Guadalupe", "Ana", "Mariana", "Jimena", "Andrea", "Victoria",
        "Lucia", "Emilia", "Catalina", "Montserrat", "Itzel", "Paulina", "Claudia",
        # Landmarks & culture
        "Aztec", "Maya", "Cactus", "Tequila", "Sierra", "Sol", "Luna", "Jaguar",
        "Chichen", "Itza", "Cancun", "Tulum", "Oaxaca", "Cabo",
        # Famous women
        "Frida", "Kahlo", "Salma", "Hayek", "Pina", "Vargas",
    ],
    # Switzerland
    "CH": [
        # Female names
        "Emma", "Mia", "Lena", "Lia", "Nora", "Anna", "Sofia", "Alina",
        "Julia", "Chiara", "Giulia", "Noemi", "Elin", "Amelie", "Lara", "Elena",
        "Sina", "Laura", "Selina", "Nadia", "Vivienne", "Eliane", "Corinne",
        "Ursula", "Heidi", "Annina", "Salome", "Rahel",
        # Landmarks & culture
        "Alps", "Bern", "Glacier", "Summit", "Crystal", "Peak", "Snow", "Yodel",
        "Matterhorn", "Zurich", "Geneva", "Lucerne", "Interlaken", "Jungfrau",
        # Famous women
        "Johanna", "Spyri", "Heidi", "Berger", "Nesbo",
    ],
    # Russia
    "RU": [
        # Female names
        "Anastasia", "Maria", "Olga", "Svetlana", "Tatiana", "Natalia",
        "Ekaterina", "Irina", "Elena", "Daria", "Anna", "Yulia", "Vera",
        "Polina", "Ksenia", "Alina", "Dina", "Galina", "Ludmila", "Nadezhda",
        "Oksana", "Raisa", "Tamara", "Valentina", "Zoya", "Varvara", "Milana", "Arina",
        # Landmarks & culture
        "Kremlin", "Bolshoi", "Hermitage", "St", "Petersburg", "Moscow",
        "Red", "Square", "Trans-Siberian", "Baikal", "Ural", "Caucasus",
        # Famous women
        "Anna", "Pavlova", "Maya", "Plisetskaya", "Svetlana", "Savitskaya",
    ],
    # Ukraine
    "UA": [
        # Female names
        "Oksana", "Olena", "Kateryna", "Yulia", "Iryna", "Natalia", "Svitlana",
        "Olya", "Hanna", "Tetiana", "Mariya", "Anna", "Viktoria", "Solomiya",
        "Ivanna", "Daryna", "Zoryana", "Halyna", "Lesya", "Nadiya", "Larysa",
        "Ruslana", "Yaroslava", "Khrystyna", "Valeriya", "Bohdana", "Oleksandra", "Alina",
        # Landmarks & culture
        "Kiev", "Lviv", "Odessa", "Carpathians", "Dnipro", "Donets",
        "Chernobyl", "Maidan", "Cossack", "Tryzub", "Vyshyvanka",
        # Famous women
        "Lesya", "Ukrainka", "Sofia", "Rotaru", "Ruslana",
    ],
    # Iran
    "IR": [
        # Female names
        "Fatemeh", "Zahra", "Maryam", "Sara", "Niloofar", "Yasmin", "Elham",
        "Leila", "Parisa", "Shirin", "Mina", "Nazanin", "Azar", "Bahar",
        "Golnaz", "Roya", "Sima", "Tara", "Vida", "Mahsa", "Setareh", "Negar",
        "Shabnam", "Golshifteh", "Anahita", "Donya", "Hanieh", "Melika",
        # Landmarks & culture
        "Persepolis", "Isfahan", "Shiraz", "Tabriz", "Qom", "Yazd",
        "Kashan", "Hamadan", "Cyrus", "Darius", "Rosewater", "Saffron",
        # Famous women
        "Shirin", "Ebadi", "Marjane", "Satrapi", "Googoosh",
    ],
    # Indonesia
    "ID": [
        # Female names
        "Siti", "Dewi", "Putri", "Ayu", "Sri", "Rina", "Intan", "Kartika",
        "Nurul", "Lestari", "Indah", "Ratna", "Wulan", "Melati", "Citra", "Maya",
        "Sekar", "Anisa", "Fitri", "Aisyah", "Laila", "Mira", "Zahra", "Tania",
        # Landmarks & culture
        "Bali", "Java", "Sumatra", "Komodo", "Borobudur", "Prambanan",
        "Rice", "Terrace", "Spice", "Island", "Volcano", "Temple",
        # Famous women
        "Suharto", "Megawati", "Sukarnoputri", "Raden", "Ajeng",
    ],
    # Malaysia
    "MY": [
        # Female names
        "Siti", "Nurul", "Aisyah", "Farah", "Mei", "Priya", "Kavitha",
        "Syafiqah", "Amira", "Zara", "Hannah", "Sarah", "Nadia", "Izzah",
        "Adibah", "Sharmila", "Devi", "Intan", "Marina", "Sofea", "Balqis",
        "Hana", "Aina", "Nisa",
        # Landmarks & culture
        "Petronas", "Twin", "Towers", "Langkawi", "Penang", "Kota",
        "Kinabalu", "Malacca", "Borneo", "Rainforest", "Batik", "Rendang",
        # Famous women
        "Michelle", "Yeoh", "Amber", "Chia", "Siti", "Nurhaliza",
    ],
    # Thailand
    "TH": [
        # Female names
        "Suda", "Malai", "Nok", "Pranee", "Siriporn", "Chanya", "Panida",
        "Duangjai", "Kannika", "Naree", "Rung", "Wilai", "Anchalee", "Busaba",
        "Chompoo", "Dao", "Fah", "Jintana", "Kulap", "Lamai", "Malee", "Nuan",
        "Somsri", "Vilai",
        # Landmarks & culture
        "Thai", "Silk", "Orchid", "Chiang", "Mai", "Phi", "Phi", "Islands",
        "Grand", "Palace", "Wat", "Arun", "Floating", "Market",
        # Famous women
        "Mom", "Chow", "Yingluck", "Shinawatra", "Sripanwa",
    ],
    # Vietnam
    "VN": [
        # Female names
        "Linh", "Lan", "Mai", "Hoa", "Huong", "Trang", "Thao", "Ngoc",
        "Anh", "Phuong", "Van", "Hanh", "Thu", "Ha", "Chi", "Nga", "Bich",
        "Dao", "Minh", "Tuyet", "Kieu", "Loan", "My", "Nhung",
        # Landmarks & culture
        "HaLong", "Bay", "Hue", "Hoi", "An", "Saigon", "Hanoi", "Delta",
        "Mekong", "Sapa", "Rice", "Paddy", "Lantern", "Festival",
        # Famous women
        "Nuong", "Hai", "Ba", "Trung", "My", "Linh",
    ],
    # Philippines
    "PH": [
        # Female names
        "Maria", "Ana", "Kristine", "Angel", "Grace", "Faith", "Princess",
        "Joy", "Liza", "Marites", "Luzviminda", "Imelda", "Corazon", "Juanita",
        "Rosario", "Mariposa", "Liwayway", "Amihan", "Tala", "Malaya", "Diwata",
        "Bituin", "Luningning", "Ilang",
        # Landmarks & culture
        "Manila", "Cebu", "Palawan", "Boracay", "Rizal", "Park", "Intramuros",
        "Rice", "Terrace", "Chocolate", "Hills", "Taal", "Volcano",
        # Famous women
        "Imelda", "Marcos", "Corazon", "Aquino", "Lea", "Salonga",
    ],
    # Taiwan
    "TW": [
        # Female names
        "Mei-ling", "Shu-fen", "Ya-wen", "Hsin-yi", "Chia-ling", "Pei-ju",
        "Yu-hsin", "Ling", "Hui", "Chen", "Li-hua", "Su-yin", "Ai-ling",
        "Fen", "Jie", "Ming-hui", "Shu-hui", "Hsiu-lan", "I-chun", "Wen-jing",
        "Chun-mei", "Yuan", "Chi", "Yun",
        # Landmarks & culture
        "Taipei", "Taipei101", "Shilin", "NightMarket", "Taroko", "Gorge",
        "SunMoon", "Lake", "Jiufen", "Tainan", "Kaohsiung",
        # Famous women
        "Soong", "Mei-ling", "Tsai", "Ing-wen", "Angela", "Chang",
    ],
    # Israel
    "IL": [
        # Female names
        "Noa", "Tamar", "Yael", "Shira", "Maya", "Michal", "Hila", "Rotem",
        "Adi", "Talia", "Rachel", "Sara", "Aviva", "Dalia", "Shoshana", "Tali",
        "Noga", "Efrat", "Rivka", "Yael", "Naomi", "Hadar", "Lior", "Ofra",
        # Landmarks & culture
        "Dead", "Sea", "Galilee", "Negev", "Jerusalem", "Tel", "Aviv",
        "Masada", "Haifa", "Eilat", "Nazareth", "Bethlehem",
        # Famous women
        "Golda", "Meir", "Hannah", "Senedh", "Gal", "Gadot",
    ],
    # Saudi Arabia
    "SA": [
        # Female names
        "Noura", "Sara", "Rania", "Lamia", "Aisha", "Huda", "Reem", "Dana",
        "Arwa", "Lujain", "Mashael", "Maha", "Joud", "Rima", "Ghada", "Abeer",
        "Hessa", "Fawzia", "Hanan", "Manal", "Shatha", "Tala", "Aljohara", "Bashaer",
        # Landmarks & culture
        "Mecca", "Medina", "Riyadh", "Jeddah", "Dammam", "Oasis",
        "Desert", "Sand", "Dune", "Camel", "Palm", "Date",
        # Famous women
        "Reema", "Bandari", "Haifa", "Wehbe", "Nora", "Fatehi",
    ],
    # Egypt
    "EG": [
        # Female names
        "Fatima", "Mariam", "Nour", "Salma", "Aya", "Hana", "Laila", "Yasmin",
        "Malak", "Farida", "Habiba", "Omnia", "Nada", "Mona", "Sama", "Rana",
        "Heba", "Amira", "Doaa", "Shaimaa", "Esraa", "Mennatallah", "Rowan", "Jana",
        # Landmarks & culture
        "Pyramid", "Sphinx", "Nile", "Luxor", "Aswan", "Cairo", "Alexandria",
        "Pharaoh", "Cleopatra", "Temple", "Valley", "Kings",
        # Famous women
        "Cleopatra", "Nefertiti", "Huda", "Shaarawi", "Faten", "Hamama",
    ],
    # Nigeria
    "NG": [
        # Female names
        "Amina", "Fatima", "Zainab", "Ngozi", "Chioma", "Adaeze", "Nneka",
        "Ifeoma", "Chiamaka", "Blessing", "Precious", "Uche", "Amaka",
        "Chidinma", "Funke", "Ijeoma", "Nkechi", "Obiageli", "Yewande",
        "Temitope", "Abimbola", "Folake", "Kehinde", "Adanna",
        # Landmarks & culture
        "Lagos", "Abuja", "Nollywood", "Sahel", "Savanna", "Benin",
        "Ife", "Benin", "City", "Osun", "Osogbo", "Sacred",
        # Famous women
        "Chimamanda", "Adichie", "Ngozi", "Okonjo", "Iweala",
    ],
    # Kenya
    "KE": [
        # Female names
        "Wanjiku", "Akinyi", "Njeri", "Atieno", "Muthoni", "Wambui",
        "Achieng", "Chebet", "Kendi", "Naliaka", "Nyambura", "Wairimu",
        "Makena", "Nekesa", "Adhiambo", "Anyango", "Kemunto", "Moraa",
        "Chepkoech", "Jendela", "Naserian", "Salome", "Nafula", "Awino",
        # Landmarks & culture
        "Safari", "Serengeti", "Nairobi", "Mombasa", "Kilimanjaro",
        "Maasai", "Mara", "Rift", "Valley", "Victoria", "Lake",
        # Famous women
        "Wangari", "Maathai", "Lupita", "Nyong'o",
    ],
    # Argentina
    "AR": [
        # Female names
        "Sofia", "Valentina", "Martina", "Catalina", "Julieta", "Camila",
        "Morena", "Agostina", "Milagros", "Lucia", "Emilia", "Victoria",
        "Bianca", "Mora", "Juana", "Paloma", "Renata", "Delfina", "Isabella",
        "Amparo", "Pilar", "Candelaria", "Malena", "Antonia",
        # Landmarks & culture
        "Buenos", "Aires", "Tango", "Pampas", "Patagonia", "Iguazu",
        "Andes", "Mendoza", "Wine", "Gaucho", "Mate", "Che",
        # Famous women
        "Eva", "Peron", "Valentina", "Tereshkova", "Borges",
    ],
    # Chile
    "CL": [
        # Female names
        "Sofia", "Martina", "Florencia", "Javiera", "Isidora", "Antonia",
        "Fernanda", "Valentina", "Emilia", "Catalina", "Josefa", "Trinidad",
        "Amanda", "Constanza", "Victoria", "Agustina", "Ignacia", "Gabriela",
        "Paula", "Magdalena", "Elisa", "Francisca", "Renata", "Colomba",
        # Landmarks & culture
        "Santiago", "Valparaiso", "Atacama", "Torres", "del", "Paine",
        "Wine", "Vineyard", "Andes", "Easter", "Island", "Moai",
        # Famous women
        "Isabel", "Allende", "Violeta", "Parra",
    ],
    # Colombia
    "CO": [
        # Female names
        "Maria", "Valentina", "Isabella", "Camila", "Sara", "Gabriela",
        "Daniela", "Laura", "Valeria", "Juliana", "Manuela", "Mariana",
        "Salome", "Luciana", "Natalia", "Carolina", "Ximena", "Ana",
        "Sofia", "Alejandra", "Isabela", "Antonia", "Emilia", "Lucia",
        # Landmarks & culture
        "Bogota", "Cartagena", "Medellin", "Coffee", "Carnival", "Barranquilla",
        "Amazon", "Orinoco", "Cocora", "Valley", "Wax", "Palm",
        # Famous women
        "Sofia", "Vergara", "Shakira", "Barranquilla",
    ],
    # Peru
    "PE": [
        # Female names
        "Maria", "Sofia", "Valentina", "Camila", "Luciana", "Brianna",
        "Aitana", "Ariana", "Danna", "Fabiana", "Xiomara", "Fatima",
        "Mia", "Naomi", "Salome", "Antonella", "Guadalupe", "Micaela",
        "Milagros", "Renata", "Mariel", "Kori", "Suyana", "Lluvia",
        # Landmarks & culture
        "Machu", "Picchu", "Cusco", "Lima", "Nazca", "Lines",
        "Amazon", "Andes", "Sacred", "Valley", "Inca", "Trail",
        # Famous women
        "Mario", "Vargas", "Llosa", "Garcia", "Marquez",
    ],
    # Portugal
    "PT": [
        # Female names
        "Maria", "Beatriz", "Leonor", "Matilde", "Carolina", "Mariana",
        "Ines", "Francisca", "Margarida", "Sofia", "Ana", "Joana", "Rita",
        "Clara", "Madalena", "Constanca", "Benedita", "Mafalda", "Teresa",
        "Catarina", "Sara", "Laura", "Eva", "Raquel",
        # Landmarks & culture
        "Lisbon", "Porto", "Algarve", "Azores", "Madeira", "Fado",
        "Pasteis", "Bacalhau", "Cork", "Olive", "Port", "Wine",
        # Famous women
        "Amalia", "Rodrigues", "Fernanda", "Pessoa",
    ],
    # Greece
    "GR": [
        # Female names
        "Maria", "Eleni", "Katerina", "Sofia", "Despina", "Georgia", "Ioanna",
        "Alexandra", "Vasiliki", "Christina", "Panagiota", "Anastasia", "Fotini",
        "Evangelia", "Konstantina", "Dimitra", "Efthymia", "Theodora", "Nikoletta",
        "Stavroula", "Angeliki", "Paraskevi", "Aikaterini", "Zoi",
        # Landmarks & culture
        "Athens", "Santorini", "Mykonos", "Crete", "Olympus", "Parthenon",
        "Acropolis", "Olive", "Grape", "Aegean", "Ionian", "Mediterranean",
        # Famous women
        "Maria", "Callas", "Helena", "Papariza",
    ],
    # Czech Republic
    "CZ": [
        # Female names
        "Eliska", "Tereza", "Anna", "Adela", "Karolina", "Natalie", "Kristyna",
        "Lucie", "Veronika", "Barbora", "Eva", "Petra", "Jana", "Hana", "Lenka",
        "Marketa", "Michaela", "Pavla", "Renata", "Simona", "Klara", "Terezie",
        "Julie", "Sofie",
        # Landmarks & culture
        "Prague", "Bohemian", "Moravian", "Charles", "Bridge", "Wenceslas",
        "Square", "Czech", "Crystal", "Beer", "Castle", "Karlstejn",
        # Famous women
        "Franz", "Kafka", "Milan", "Kundera",
    ],
    # Austria
    "AT": [
        # Female names
        "Anna", "Emma", "Mia", "Lena", "Sophie", "Marie", "Johanna",
        "Katharina", "Julia", "Lisa", "Laura", "Teresa", "Amelie", "Hannah",
        "Valentina", "Elena", "Nina", "Clara", "Isabella", "Marlene", "Leonie",
        "Sarah", "Melanie", "Elisabeth",
        # Landmarks & culture
        "Vienna", "Salzburg", "Innsbruck", "Waltz", "Mozart", "Sacher",
        "Schnitzel", "Alps", "Danube", "Schonbrunn", "Hofburg", "Belvedere",
        # Famous women
        "Sissi", "Empress", "Niki", "Lauda",
    ],
    # Belgium
    "BE": [
        # Female names
        "Emma", "Louise", "Olivia", "Alice", "Juliette", "Marie", "Elise",
        "Camille", "Charlotte", "Nora", "Anna", "Lotte", "Fien", "Lise",
        "Manon", "Margaux", "Ines", "Leonie", "Amelie", "Jeanne", "Maya",
        "Eva", "Amber", "Eline",
        # Landmarks & culture
        "Brussels", "Bruges", "Ghent", "Antwerp", "Chocolate", "Waffle",
        "Beer", "Diamond", "Manneken", "Pis", "Grand", "Place",
        # Famous women
        "Adeline", "Hergy", "Julie", "Tatham",
    ],
    # Denmark
    "DK": [
        # Female names
        "Emma", "Freja", "Ida", "Clara", "Laura", "Sofia", "Astrid", "Signe",
        "Mathilde", "Camilla", "Mette", "Hanne", "Lene", "Bente", "Birgit",
        "Inge", "Karin", "Rikke", "Sanne", "Maja", "Alma", "Agnes", "Liva", "Nora",
        # Landmarks & culture
        "Copenhagen", "Tivoli", "Nyhavn", "Viking", "Lego", "Hygge",
        "Mermaid", "Little", "Christiania", "Strorget", "Amalienborg",
        # Famous women
        "Karen", "Blixen", "Hans", "Christian", "Andersen",
    ],
    # Romania
    "RO": [
        # Female names
        "Maria", "Elena", "Ioana", "Andreea", "Alexandra", "Gabriela",
        "Cristina", "Ana", "Daria", "Bianca", "Mihaela", "Simona", "Camelia",
        "Alina", "Georgiana", "Ramona", "Doina", "Flavia", "Corina", "Daniela",
        "Ioana", "Iulia", "Teodora", "Raluca",
        # Landmarks & culture
        "Bucharest", "Transylvania", "Dracula", "Carpathians", "Danube",
        "Bran", "Castle", "Painted", "Monasteries", "Moldavia",
        # Famous women
        "Elisa", "Vianu", "Ana", "Blandiana",
    ],
    # Bulgaria
    "BG": [
        # Female names
        "Maria", "Elena", "Iva", "Nadezhda", "Yana", "Ralitsa", "Gergana",
        "Svetlana", "Milena", "Desislava", "Petya", "Vanya", "Tsvetelina",
        "Ivanka", "Margarita", "Silvia", "Vesela", "Kamelia", "Radka", "Ani",
        "Eli", "Bilyana", "Dobrinka", "Rumyana",
        # Landmarks & culture
        "Sofia", "Plovdiv", "Varna", "Burgas", "Rila", "Monastery",
        "Rose", "Valley", "Balkan", "Thrace", "Black", "Sea",
        # Famous women
        "Borisova", "Dimitrova", "Stefka", "Kostadinova",
    ],
    # Hungary
    "HU": [
        # Female names
        "Anna", "Hanna", "Zsofia", "Lili", "Emma", "Luca", "Boglarka",
        "Fanni", "Lilla", "Eszter", "Judit", "Eva", "Katalin", "Zsuzsanna",
        "Ilona", "Edit", "Agnes", "Klaudia", "Reka", "Noemi", "Vivien",
        "Dorina", "Szofia", "Petra",
        # Landmarks & culture
        "Budapest", "Danube", "Buda", "Pest", "Thermal", "Bath", "Goulash",
        "Paprika", "Tokaj", "Wine", "Parliament", "Fisherman",
        # Famous women
        "Elizabeth", "Bathory", "Agatha", "Christie",
    ],
    # Ireland
    "IE": [
        # Female names
        "Aoife", "Ciara", "Niamh", "Saoirse", "Siobhan", "Grainne", "Aisling",
        "Eabha", "Roisin", "Orla", "Maeve", "Deirdre", "Sinead", "Bronagh",
        "Caoimhe", "Clodagh", "Fionnuala", "Imelda", "Kathleen", "Mary",
        "Erin", "Riona", "Bridget", "Nuala",
        # Landmarks & culture
        "Dublin", "Cork", "Galway", "Shamrock", "Leprechaun", "Guinness",
        "Celtic", "Trinity", "Cliffs", "Moher", "Giant", "Causeway",
        # Famous women
        "Sinead", "O'Connor", "Enya", "Maeve", "Binchy",
    ],
    # New Zealand
    "NZ": [
        # Female names
        "Charlotte", "Olivia", "Isla", "Ava", "Mia", "Harper", "Ruby", "Willow",
        "Grace", "Sophie", "Lily", "Eva", "Amelia", "Chloe", "Georgia", "Poppy",
        "Hazel", "Ivy", "Freya", "Matilda", "Maia", "Aroha", "Whetu", "Moana",
        # Landmarks & culture
        "Auckland", "Wellington", "Queenstown", "Hobbit", "Milford", "Sound",
        "Rotorua", "Tongariro", "Abel", "Tasman", "Maori", "Kiwi",
        # Famous women
        "Kate", "Sheppard", "Edmund", "Hillary",
    ],
}

DEFAULT_GIRL_NAMES = [
    # Female names
    "Ava", "Bella", "Chloe", "Daisy", "Elena", "Freya", "Grace", "Hazel",
    "Ivy", "Jade", "Kira", "Luna", "Mila", "Nina", "Olivia", "Poppy",
    "Quinn", "Ruby", "Sofia", "Tara", "Uma", "Vera", "Willow", "Yara", "Zoe",
    "Aria", "Nova", "Iris", "Luna", "Stella", "Aurora", "Celeste",
]


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
    """Rename a config with a unique female name specific to its country."""
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