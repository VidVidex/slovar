import requests
import fitz
import sqlite3
import time
from dataclasses import dataclass
import argparse

#
# cel repozitorij: source=dk
# fri: source=25
#

REQUESTS_DELAY = 0.5


@dataclass
class Oseba:
    ime: str
    priimek: str


@dataclass
class Organizacija:
    id: str
    ime_kratko: str
    ime_dolgo: str


@dataclass
class Stran:
    stevilka_strani_skupaj: int  # Številka strani gledano od začetka dokumenta
    stevilka_strani_pdf: int  # Številka strani, ki je prebrana iz pdfja
    text: str


@dataclass
class Datoteka:
    id: int
    url: str
    strani: list[Stran]


@dataclass
class Gradivo:
    id: int
    avtorji: list[Oseba]
    naslov: str
    leto: int
    organizacije: list[Organizacija]
    repozitorij_url: str
    datoteke: list[Datoteka] = None


def extract_strani(url) -> list[Stran]:
    """
    Iz PDFja na danem urlju prebere text in ga vrne v obliki strani
    """
    try:
        response = requests.get(url)

        if response.status_code != 200:
            print(
                f"Napaka pri branju datoteke iz naslova {url}: "
                + str(response.status_code)
            )
            return []

        with fitz.open(stream=response.content) as doc:
            strani = []

            i = 1
            for page in doc:
                strani.append(
                    Stran(
                        stevilka_strani_skupaj=i,
                        stevilka_strani_pdf=page.get_label(),
                        text=page.get_text(),
                    )
                )
                i += 1

            return strani

    except:
        print(f"Napaka pri branju datoteke iz naslova {url}")
        return []


def json_to_gradivo(gradivo) -> Gradivo:
    """
    Iz response jsona prebere podatke o gradivu
    """
    osebe = []
    for avtor in gradivo["Osebe"]:
        osebe.append(Oseba(ime=avtor["Ime"], priimek=avtor["Priimek"]))

    organizacije = []
    for organizacija in gradivo["Organizacije"]:
        organizacije.append(
            Organizacija(
                id=organizacija["OrganizacijaID"],
                ime_kratko=organizacija["Naziv"],
                ime_dolgo=organizacija["Kratica"],
            )
        )

    datoteke = []
    for datoteka in gradivo["Datoteke"]:
        strani = extract_strani(datoteka["PrenosPolniUrl"])
        datoteke.append(
            Datoteka(id=datoteka["ID"], url=datoteka["PrenosPolniUrl"], strani=strani)
        )

    return Gradivo(
        id=gradivo["ID"],
        avtorji=osebe,
        organizacije=organizacije,
        naslov=gradivo["Naslov"],
        leto=gradivo["LetoIzida"],
        repozitorij_url=gradivo["IzpisPolniUrl"],
        datoteke=datoteke,
    )


def db_dodaj_organizacijo(conn, organizacija: Organizacija, gradivo: Gradivo):
    """
    Doda organizacijo v tabelo organizacij če še ni ter doda povezavo med gradivom in organizacijo
    """

    cursor = conn.cursor()

    print(f"    Dodajam organizacijo {organizacija.ime_kratko}")
    cursor.execute(
        "INSERT OR IGNORE INTO organizacije VALUES (?, ?, ?)",
        (organizacija.id, organizacija.ime_dolgo, organizacija.ime_kratko),
    )
    conn.commit()

    print("    Dodajam povezavo med organizacijo in gradivom")
    cursor.execute(
        "INSERT OR IGNORE INTO gradiva_organizacije (gradivo_id, organizacija_id) VALUES (?, ?)",
        (gradivo.id, organizacija.id),
    )
    conn.commit()


def db_dodaj_osebe(conn, oseba: Oseba, gradivo: Gradivo):
    """
    Doda osebo v tabelo oseb če še ni ter doda povezavo med gradivom in osebo
    """

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM osebe WHERE ime = ? AND priimek = ?",
        (oseba.ime, oseba.priimek),
    )
    result = cursor.fetchall()

    if len(result) != 0:
        print(f"    Oseba {oseba.ime} {oseba.priimek} že obstaja")

    else:
        print(f"    Dodajam osebo {oseba.ime} {oseba.priimek}")
        cursor.execute(
            "INSERT INTO osebe (ime, priimek) VALUES (?, ?)",
            (oseba.ime, oseba.priimek),
        )

        conn.commit()

    cursor.execute(
        "SELECT id FROM osebe WHERE ime = ? AND priimek = ?",
        (oseba.ime, oseba.priimek),
    )
    id = cursor.fetchone()[0]

    print("    Dodajam povezavo med osebo in gradivom")
    cursor.execute(
        "INSERT OR IGNORE INTO gradiva_osebe (gradivo_id, oseba_id) VALUES (?, ?)",
        (gradivo.id, id),
    )
    conn.commit()


def db_dodaj_gradivo(conn, gradivo: Gradivo):
    """
    Doda gradivo v db
    """

    cursor = conn.cursor()

    print(f"    Dodajam gradivo v bazo")
    cursor.execute(
        "INSERT OR IGNORE INTO gradiva (id, naslov, leto, repozitorij_url) VALUES (?, ?, ?, ?)",
        (gradivo.id, gradivo.naslov, gradivo.leto, gradivo.repozitorij_url),
    )
    conn.commit()


def db_dodaj_datoteko(conn, datoteka: Datoteka, gradivo: Gradivo):
    """
    V bazo doda datoteko in povezavo z gradivom
    """

    cursor = conn.cursor()

    print(f"    Dodajam datoteko iz naslova {datoteka.url}")
    cursor.execute(
        "INSERT OR IGNORE INTO datoteke (id, url, gradivo_id) VALUES (?, ?, ?)",
        (datoteka.id, datoteka.url, gradivo.id),
    )
    conn.commit()

    print(f"      Dodajam {len(datoteka.strani)} strani")
    for stran in datoteka.strani:
        cursor.execute(
            "INSERT OR IGNORE INTO strani (datoteka_id, stevilka_strani_skupaj, stevilka_strani_pdf, text) VALUES (?, ?, ?, ?)",
            (
                datoteka.id,
                stran.stevilka_strani_skupaj,
                stran.stevilka_strani_pdf,
                stran.text,
            ),
        )
    conn.commit()


def get_gradiva(conn, json):
    """
    Iz response jsona prebere podatke o gradivih in jih vrne. Ta gradiva še ne vsebujejo vsebine datotek.
    """

    for result in json["results"]:
        gradivo = json_to_gradivo(result)

        if (
            gradivo.datoteke == None
            or len(gradivo.datoteke) == 0
            or len(gradivo.datoteke[0].strani) == 0
        ):
            print(f"  Gradivo {gradivo.naslov} nima datotek")
            continue

        print(f"  Dodajam gradivo {gradivo.naslov}")

        for organizacija in gradivo.organizacije:
            db_dodaj_organizacijo(conn, organizacija, gradivo)

        for oseba in gradivo.avtorji:
            db_dodaj_osebe(conn, oseba, gradivo)

        db_dodaj_gradivo(conn, gradivo)

        for datoteka in gradivo.datoteke:
            db_dodaj_datoteko(conn, datoteka, gradivo)

        time.sleep(REQUESTS_DELAY)


def scrape_faks(conn, source_id=25, start_page=1):
    """
    V sistem prenese vse diplome z določenega faksa
    """

    page = start_page
    while True:
        print(f"Prenašam stran {page} za organizacijo {source_id}")

        url = f"https://repozitorij.uni-lj.si/ajax.php?cmd=getAdvancedSearch&source={source_id}&workType=0&language=0&fullTextOnly=1&&page={page}"

        try:
            response = requests.get(url)
        except:
            print(f"Napaka pri prenašanju iz naslova {url}")
            continue

        if response.status_code != 200:
            print(f"Napaka pri prenašanju iz naslova {url}: {response.status_code}")
            page += 1
            if page > response_json["pagingInfo"]["numberOfPages"]:
                break
            time.sleep(REQUESTS_DELAY)

        response_json = response.json()

        get_gradiva(conn, response_json)

        page += 1
        if page > response_json["pagingInfo"]["numberOfPages"]:
            break

        time.sleep(REQUESTS_DELAY)


def create_schema(conn):
    """
    Poskrbi da tabele v bazi obstajajo
    """

    cursor = conn.cursor()

    print(f"Ustvarjam tabele če še ne obstajajo")
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS gradiva
                 (id INTEGER PRIMARY KEY,
                  naslov TEXT,
                  leto INTEGER,
                  repozitorij_url TEXT)"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS osebe
                 (id INTEGER PRIMARY KEY,
                  ime TEXT,
                  priimek TEXT)"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS organizacije
                 (id INTEGER PRIMARY KEY,
                  ime_kratko TEXT,
                  ime_dolgo TEXT)"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS datoteke
                 (id INTEGER PRIMARY KEY,
                  url TEXT,
                  gradivo_id INTEGER,
                  FOREIGN KEY(gradivo_id) REFERENCES gradiva(id))"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS strani
                 (id INTEGER PRIMARY KEY,
                  datoteka_id INTEGER,
                  stevilka_strani_skupaj INTEGER,
                  stevilka_strani_pdf INTEGER NULL,
                  text TEXT,
                  FOREIGN KEY(datoteka_id) REFERENCES datoteke(id))"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS gradiva_osebe
                 (gradivo_id INTEGER,
                  oseba_id INTEGER,
                  PRIMARY KEY(gradivo_id, oseba_id),
                  FOREIGN KEY(gradivo_id) REFERENCES gradiva(id),
                  FOREIGN KEY(oseba_id) REFERENCES osebe(id))"""
    )

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS gradiva_organizacije
                 (gradivo_id INTEGER,
                  organizacija_id INTEGER,
                  PRIMARY KEY(gradivo_id, organizacija_id),
                  FOREIGN KEY(gradivo_id) REFERENCES gradiva(id),
                  FOREIGN KEY(organizacija_id) REFERENCES organizacije(id))"""
    )

    conn.commit()


def drop_tables(conn):
    """
    Izbriše vse tabele v bazi
    """
    cursor = conn.cursor()

    print(f"Brišem tabele v bazi")
    cursor.execute("DROP TABLE IF EXISTS gradiva")
    cursor.execute("DROP TABLE IF EXISTS osebe")
    cursor.execute("DROP TABLE IF EXISTS organizacije")
    cursor.execute("DROP TABLE IF EXISTS datoteke")
    cursor.execute("DROP TABLE IF EXISTS strani")
    cursor.execute("DROP TABLE IF EXISTS gradiva_osebe")
    cursor.execute("DROP TABLE IF EXISTS gradiva_organizacije")


if __name__ == "__main__":
    conn = sqlite3.connect("slovar.db")

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    recreate_parser = subparsers.add_parser(
        "recreate-schema", help="Izbriši in ustvari tabele v bazi"
    )

    scrape_parser = subparsers.add_parser(
        "scrape", help="V bazo shrani gradiva z določenega faksa"
    )
    scrape_parser.add_argument(
        "id",
        type=int,
        help="ID faksa, ki ga želimo prenesti. 11 = FMF, 25 = FRI, 27 = FE. Ostalo: https://repozitorij.uni-lj.si/ajax.php?cmd=getSearch",
    )

    args = parser.parse_args()

    if args.command == "recreate-schema":
        drop_tables(conn)
        create_schema(conn)
    elif args.command == "scrape":
        scrape_faks(conn, source_id=args.id)

    args = parser.parse_args()

    conn.close()
