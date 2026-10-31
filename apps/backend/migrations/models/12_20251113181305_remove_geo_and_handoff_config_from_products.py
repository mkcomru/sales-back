from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."products" DROP COLUMN IF EXISTS "geo_config";
        ALTER TABLE "backend"."products" DROP COLUMN IF EXISTS "handoff_config";
        ALTER TABLE "backend"."products" DROP COLUMN IF EXISTS "fields_config";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "backend"."products" ADD "geo_config" JSONB NOT NULL DEFAULT '{}';
        ALTER TABLE "backend"."products" ADD "handoff_config" JSONB NOT NULL DEFAULT '{}';
        ALTER TABLE "backend"."products" ADD "fields_config" JSONB NOT NULL DEFAULT '{}';"""


MODELS_STATE = (
    "eJztXf9P2zgU/1ei/rSTNsS4sZvQ6aQWytYbtKyE224wRW7qthGJXdxkpZr43892vn9xaN"
    "KmTQ7/soHt59gf2+99/PxsfrUsPIbm4uAU2HCKyap1ovxqIWBB+kMq77XSAvN5mMMSbDAy"
    "eWHdLWVAngxGC5sA3aY5E2AuIE0aw4VOjLltYERTkWOaLBHrtKCBpmGSg4wHB2o2nkJ7Bg"
    "nNuP1Bkw00ho+0cu/X+b02MaA5jjXYGLNv83TNXs15Wg/Z57wg+9pI07HpWCgsPF/ZM4yC"
    "0gayWeoUIkhoh1j1NnFY81nrvL76PXJbGhZxmxiRGcMJcEw70t01MdAxYvjR1ix4B6fsK2"
    "+O3r77492H39+/+0CL8JYEKX88ud0L++4KcgT6auuJ5wMbuCU4jCFu/P8UcqczQLKh88sn"
    "wKNNToLnQ5WHnp8QwhdOmS3hZ4FHzYRoas8YaMfHOWj90x6efmoPX9FSv7HeYDqN3Rne97"
    "KO3DwGaQhhtGUpJFX4KJiECbGmAJqDn9r9prJGW4vFgxmF7dVl+xtH1Fp5OReD/ke/eATm"
    "04tBJ4EucUxXr6yLayAgEc1GFD4Ca14Q1KjM7nBttZqD6hKT+4mJl0VQjcrI2ZqNq46tOU"
    "ArrZCBjws9b+jrAe02bD0jSJP7TFPvgZKG8RwTaEzRZ7jiaPZoowDSs8y8TwvDmuqH4pM/"
    "GfzUkJQRsAyoY2KO0E7SrkHbpT/t69P2WbfF0RwB/X4JyFgTwepxZEpbsakRaALW4gzt2v"
    "EqOv889ArlIOxVqtI6mwVzbPF6eG0ERbDCn8HAG+O6QTAneOzo9oYgXLm1NAsGtnrwEY6s"
    "mth6SmdZR1YyBSAw5a1m32ZfylogOTtXfwE9u3t11+96O9iWOiPYmc4UXokywUTxv/eGfV"
    "C5pIpFxexfxVcIB60EmKUrydgl3wa94F1jff4hd87V7pyDeVOMmcSlXhI1iWpFbisLAReR"
    "eEmg5fG5yJLflNBFqqofjmszuvjayqZ0yVm4BfSaR9KSyEUWV1EiXKmR9/YZWfY93ILkmH"
    "ZeSPqlG2hdpV9a+qVr7ZeSfultI2pjBDU80X5iQ89Y+2JkU4IS4WyEwWJhMDJja0XVa1qy"
    "KRjvQNE+OMA0JobOt+hamYMAcQ1NgXnXUzmOWJkjLXENEnPRUYxpQp3DVVR/ZIjuGeWWOo"
    "MKa4uCJwpl9UrYRMVAysOYAJd410LFUN07hQu2kZsY0zTwf18P+tnApwQTsN8g2uHbsaHb"
    "rxWTqvgflZ3l/jlxkAvvyDFM20CLA/bBv6o542WI5C+A5Fxn2OCFPSW8Fl5BcgF4vnxNwP"
    "3Eo5ASlKNQfhR0YmkTTLh7wYI24HvIe7gqNCK5lcjR2Wx0vB5pXPlkunlzLIVAfodRJ1fD"
    "wWn3+rp7tgHscZtwfLiGSTg+FFoElpWG2fWbEQ3YNkTctpYFPL+mUtDv/hyyCshT7vcCEQ"
    "FGlo0oEwRQa/aZf/rtB1lsNTbCrbN5Xvd4aAR42DQwov2lyf3fYWhIXTGwoQmnBFjaCG8a"
    "IKJ6VXVwTQ9D9xMlElEV4kOkNWJEImqsfIiIW8lmESLr1JEdIBIemMn4kNYu4kNk4KqMDp"
    "HRvjWJcFgn2leGhjQnNISR3wyL7nFisSX3abeMBqmbLsu1pcJQtxy/RkSmKSc6OzmshIui"
    "ISFRmaZAufOzdbRYQlIE1VBCYpqN6T1cLTHJ8hKIHftRGenH38CPL7cvkomXmKAV37urlF"
    "Om+FrSz5jDKwN3pmSWdVubecxSxhlLRllT9uPyQxeXzBnaRY6VshwZFDOoYt8hV9fqsNf/"
    "eKK4QN+h/s1lpztkpa0RJHeoMxhcdNv9E2WEsQkBukNdWuREgbRA0jm+t+lO4INjEJihbz"
    "tuqwXh3xGxxDiMKnQSFTVB6895NlixOd/pJSc1H95Xbzm6tJDhWvm0v3d/Vyn3EKWwZV+5"
    "5OmlofOj8gpBFxd6QZNO7nCqOmvYz0Xe+jwUkcKv6D3eefg6xob4NfGdjSR8cQ1V/mEbPN"
    "9CsBbHfRDcJmzOoq40LiWKisjfEIL2jNdBiwzUdp0Pt+4HWMU/gUkHhHYqkobJmJaTgSQV"
    "uyhc6FPQiX0UgUBTdtY72LW5c3X9+ReU3x05Ptz3FEwEZxbjxVGRl7ShyKHFgaLckJQ0MM"
    "w1yUmis6NOLn+f72UY4QgVFBvg6Otu0vFft7WZZ1Wl418+MFJr9790im7NEEsHSwkHyzou"
    "gvDUe0MPQaPgrNQ1QGmHNRcREpbzHB+hZSQdaRwdoZMB2Zud9cZq2I5VLYlqazi4UdnBLs"
    "GOzQ52v9y0L3rnPZbkPbvCUk/bavfjYPiv1v121R2qJ0qgl+DjHJJSr29UcNMaI3YpugjD"
    "iYhIdhOymwKXqavUsNGrkhlqNnGTUqxrU7c3pcZtksaln0NQtzEp+l5CQm6vmrbkdvDt4T"
    "pqkpYS6kmeF1eUdBnQCXwPMzaDYjRjQk1RljvYWzN9U5YJ+LI7fDIFODZupXlA+0YdnCgs"
    "8w597XY+DQafT5QlHM0wvr9DV4OLCx4PNsemyfAuA/46E/lIPI+P0vZ+BugCN3O4mEAvJO"
    "R2iL5vidIjUHJKb59FeYOuLaBOYAaZEuOalmzkezSVaAkfmzmg3yiBqS8nEQ30rvcWWBpN"
    "8ZWjqEydrhyxzzbpyhFEDIGigbURqR3G1Qb0rM5htQSyXmsgQ9+e0RzbsKDAlsUkE7COPd"
    "ED/4eakjTah/EAmatW8PKOcIfbu+xeq+3LqxjwZ221y3KOYltcP/XV+8Q0DypRvvbUTwr7"
    "Vfk+6HeTMz8op35nUWycOmkILzUwjvB+P9UHJjawznxccmDjknJg9zqwwtfSZCy3jEguYk"
    "cafOdS9DTX829yrf8Wl3S71cjttt+4i/+Bm01GXVR66ZJMHQuirOcYxRvAmNC+doCV4by1"
    "vV6B8x/553UFlj2TL8rXdauOymhDYuizLKLi5eRSFRCWkVylQVzlJySLTDObc/ciFGmKid"
    "2BV5UtjQIgesWbCWAlpE8YhJLzFy6EQSiSkpShJNs3L0//AVhbEsE="
)
