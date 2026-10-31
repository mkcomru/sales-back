from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "backend"."uid_products_product_68802a";
        ALTER TABLE "backend"."products" DROP CONSTRAINT IF EXISTS "fk_products_companie_e14c21ee";
        CREATE TABLE IF NOT EXISTS "backend"."categories" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "rules" TEXT NOT NULL,
    "examples" JSONB NOT NULL,
    "product_search_config" JSONB NOT NULL,
    "companies_id" INT NOT NULL REFERENCES "backend"."companies" ("id") ON DELETE CASCADE
);
        ALTER TABLE "backend"."fields" ADD "product_id" INT;
        ALTER TABLE "backend"."fields" ADD "category_id" INT;
        ALTER TABLE "backend"."products" ADD "category_id" INT;
        ALTER TABLE "backend"."products" DROP COLUMN "product_key";
        ALTER TABLE "backend"."products" DROP COLUMN "companies_id";
        ALTER TABLE "backend"."fields" ADD CONSTRAINT "fk_fields_categori_161dfd6f" FOREIGN KEY ("category_id") REFERENCES "backend"."categories" ("id") ON DELETE CASCADE;
        ALTER TABLE "backend"."fields" ADD CONSTRAINT "fk_fields_products_fa27eaad" FOREIGN KEY ("product_id") REFERENCES "backend"."products" ("id") ON DELETE CASCADE;
        ALTER TABLE "backend"."products" ADD CONSTRAINT "fk_products_categori_04d6e109" FOREIGN KEY ("category_id") REFERENCES "backend"."categories" ("id") ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."products" DROP CONSTRAINT IF EXISTS "fk_products_categori_04d6e109";
        ALTER TABLE "backend"."fields" DROP CONSTRAINT IF EXISTS "fk_fields_products_fa27eaad";
        ALTER TABLE "backend"."fields" DROP CONSTRAINT IF EXISTS "fk_fields_categori_161dfd6f";
        ALTER TABLE "backend"."fields" DROP COLUMN "product_id";
        ALTER TABLE "backend"."fields" DROP COLUMN "category_id";
        ALTER TABLE "backend"."products" ADD "product_key" VARCHAR(255) NOT NULL UNIQUE;
        ALTER TABLE "backend"."products" ADD "companies_id" INT NOT NULL;
        ALTER TABLE "backend"."products" DROP COLUMN "category_id";
        DROP TABLE IF EXISTS "backend"."categories";
        ALTER TABLE "backend"."products" ADD CONSTRAINT "fk_products_companie_e14c21ee" FOREIGN KEY ("companies_id") REFERENCES "backend"."companies" ("id") ON DELETE CASCADE;"""


MODELS_STATE = (
    "eJztnP9P2zgUwP+VqD/tJG5iHNwmdDqpdGXHjbWslBMSTJGbOmlEYhfHGVQT//vZTtJ8c9"
    "KmTUsi/BNg+zn2xy/2e88v/Oq4eAod730PUGhhsuicar86CLiQ/ZKrO9A6YD6Pa3gBBRNH"
    "NDaCVjYUxWDiUQIMympM4HiQFU2hZxB7Tm2MWCnyHYcXYoM1tJEVF/nIfvShTrEF6QwSVn"
    "H3gxXbaAqfWefhn/MH3bShM00N2J7yZ4tynS7mouwC0XPRkD9tohvY8V0UN54v6AyjZWsb"
    "UV5qQQQJmxDvnhKfD5+PLpxrNKNgpHGTYIgJmSk0ge/QxHTXZGBgxPmx0XhighZ/yu9HH4"
    "4/Hn/648/jT6yJGMmy5ONLML147oGgIDAYd15EPaAgaCEwxtzEzxy53gwQObqofQYeG3IW"
    "XoSqjF5UEOOLVaYmfi541h2ILDrj0E5OSmj91x31/umO3rFWv/HZYKbGgYYPwqqjoI4jjR"
    "EmR5YjOYbPBUqYEWsL0BJ+4/7tmA/a9bxHJ4nt3bfurSDqLsKay+HgS9Q8gbl3OTzL0CW+"
    "E+wr63JdCiiicqLwGbhzKdR/r4cDOdSkTIbrDWLzvZvaBj3QHNujP3ZFufOX6SOD09Umvu"
    "1QG3nv+QP/7uyEPYdRzj6LmbPBHrWI6EV0kGU/J3jqG1T3ICDGjAFGpm1VWYjCDpq0Kvyx"
    "bVoVA7tzgJj9olcyI7Jiqw2KZmw4ddgU3BAzH6QmxRJLHuU5JtC20Fe4EEQv2LAAMmQGRW"
    "SAir4WzeT4EilEVBqbfwQ8LY3UnJ6wabLJQRqYWt3rXvdzvyOIToDx8ATIVC9AG5bluJ6F"
    "cudfR9ABBSZFiHSpyyuAhjNpAE/ZDrolhKugl3Zh4BqCj3BCM1I6k69yj9xsCUDAEqPmz+"
    "ZPyrxoMicwfgdLfMDkS69cwKZt1wfKBVQuYFsdFuUC1k2UYgR1bOo/sW1I3v1isjlBRVhO"
    "mCFzoHCL9Kr7q0T0lSl3xjOo8bFo2NTYsazFQ9RspD1OCQhOzkZsxsynsJitXd23zgk2ya"
    "duW6SDQuLaCDh6QLXKOkhE1UpsH3MqOEZXx5qKjlO1ChVWQegy82v0iKrLnCk+wKobVEEf"
    "TVqbtsX/JjYbz7NuYiIcaRdSILylB7io9MKs6qdJa9S29ydkG04qOBqk4dpiw6qki/0ZWJ"
    "2r0bDXv77uf94CftqKOjlcw4g6OSy0oXiVJKK7TkAyffW/eTwumWjQWOehPDBpgsdtI7Pd"
    "722e/x5j001isMuoLNcISUQ2VJTiaGykiyoQ26ZArJHYBNcOFiRk2hKL2UMMgE3FqxqNTc"
    "q0BeW+w1oAeU+QVKEaSyimcqbMO3jCRHZ0FnsaSRnlVWyb+bHYJO9jobI+8lkfkrPrLed8"
    "LDbM+NipTZmz17LGd4ldubTxlWXZtHezzLJUV/zKomyo9SOASFWzj3w3d2SkL4pC2de+Hr"
    "0ejy4GX061AO09Gtx8O+uPeGt3Ask9OhsOL/vdwak2wdiBAN2jPmtyqkHWoDHXpgQ++jaB"
    "kh32LBh1Qa5FQiyzDny2u1qIqofO+lrOFyul5WcXWTUWy/vug6DLGtnBuR5tw3mHvqJ5mZ"
    "bayL7cf9ZiPUeYssxrQBfdDlZClxZ6Q0qnfJo6fRrZ9lcHv/Xvh5qTsJ3jl97YVwOcx1nq"
    "W/JrY757Fl96h9r8IwosRljHTdVwmbrbnpd6t/dVCSpFEYYY2oo4g55YqHrDDXfBA3jHP4"
    "HDFoRNKlGGyZS1+6GCErsNSgToc+iKoxJLgbb40nvw2gJdXV//lu33ZxwfvrYKZnIUqtnF"
    "SZG35FCUmMXLjXJLo6SF2R5ZmySpHU0K8kf2nuQQTpiCxQdw8itLFepv2rtZdqqqUL/6mq"
    "/RAX/Lt9l2Y6Nqn/SlpRRbOVsTPnkzLPs4vjiVJCmjUkk2TyUJNuMNPjvLCTZpFdr2KYcF"
    "8QZLkJZS/DfnPwNoik1zgzXIS6p12OLzS4wdT3/0gWOzZ0oiBCWfX+ZFm7QSbTsXApyFof"
    "xV65AQVKuwRaKnuoqv7VZUXetVv9Zb52Iqzq7c8l6qVTh3eiF1RbA7LwqD8ZqDFVEw1kYF"
    "wVoXBGPKgKi+TWphuod64g0bUu2Mhjdjnk5IsE95OuH3m+7lxfkFL1paaffoajT8fNMb6/"
    "3bq/5ofKpF1+XweQ7JRv+dpZ7vitNJXYhCJLGCigM/CREV9YmjPhW+1t7l/tqFxDZmsv01"
    "rCndX0HcRm2vLdpef0LiSYPjJXf3sUhbXuM93DTwV6MCxLB5OwF+OFznOGGtCgGKujUPlG"
    "K3uvhA2ZtDvbPjpTbX+VWPl5f/ARGqcXQ="
)
