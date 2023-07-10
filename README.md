# Simulateur d'implantation de station de recharge électrique

Ce simulateur se base sur un ensemble d'open data pour estimer la quantité d'énergie qui serait consommé par une station de recharge pour une localisation donnée. Le résultat dépend de nombreux paramètre et ne doit pas être pris tel quel, mais plutôt servir d'outil de réflexion.

## Installation

**NB :** Il est conseillé d'utiliser un environnement virtuel en phase de test.

Premièrement installez les dépendances avec pip :

    python -m pip install -r requirements.txt

Ensuite vous pouvez utiliser le script init_db pour construire et initialiser la base de donnée que le simulateur utilisera. Vous aurez besoin de télécharger les fichiers d'open data listés dans le paragraphe plus bas.

Lancez la série de commande suivante pour initialiser la base de donnée :

    python app/init_db.py cities files/admin_exp_folder
    python app/init.db.py cars files/cars.csv
    python app/init.db.py workflux files/flux.csv
    python app/init.db.py tmja files/tmja.csv

Dans les exemples ci-dessus remplacez le path "files" par le chemin des fichiers téléchargés.

## Lancer le serveur

Pour lancer le serveur, utilisez la commande flask :

    flask --app app/app --run

Cliquez sur le lien afficher pour accéder au simulateur.

## Data sources

Le simulateur se base sur un ensemble d'open data. Il vous faudra les télécharger au préalable :

- ADMIN EXPRESS : découpage administratif géré par l'IGN : [Disponible ici]("https://geoservices.ign.fr/adminexpress#telechargement"), utilisé pour la commande "cities"
- Voitures particulières immatriculées par commune et par type de recharge : [Disponible ici]("https://www.data.gouv.fr/fr/datasets/voitures-particulieres-immatriculees-par-commune-et-par-type-de-recharge/"), utilisé pour la commande "cars"
- Mobilités professionnelles en 2019 : déplacements domicile - lieu de travail [Disponible ici]("https://www.insee.fr/fr/statistiques/6454112") utilisé pour la commande "workflux"
- Trafic moyen journalier annuel sur le réseau routier national : [Disponible ici]("https://www.data.gouv.fr/fr/datasets/trafic-moyen-journalier-annuel-sur-le-reseau-routier-national/") utilisé pour la commande "tmja"

## Dépendance JS

Le projet utilise [Leaflet]("https://github.com/Leaflet/Leaflet") et [jQuery](https://github.com/jquery/jquery"), les versions "min" sont fournis dans le projet. Les licenses sont disponible dans le dossier "licenses".