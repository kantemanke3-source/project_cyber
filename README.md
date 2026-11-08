# CS HAGAD v2 — Application graphique de gestion scolaire

## Installation Debian
```bash
sudo apt update
sudo apt install -y python3 python3-tk python3-reportlab python3-openpyxl
```
Extraire le ZIP, ouvrir un terminal dans le dossier puis :
```bash
python3 cs_hagad.py
```

## Première connexion
- Identifiant : `admin`
- Mot de passe : `Admin@123`
- Le compte est Directeur. Créer des comptes nominatifs depuis l'onglet Utilisateurs.
- Changer le mot de passe initial dès la première utilisation (dans cette version, créer un nouveau compte Directeur avec un mot de passe personnel puis désactiver l'ancien compte après validation).

## Modules
- Connexion graphique avec logo CS HAGAD.
- Rôles : Directeur, Comptable, Secrétaire, Surveillant, Enseignant.
- Scolarité : élèves, classes, matières, inscriptions, paiements.
- Notes : saisie par matière, période et année scolaire.
- Documents : bulletins PDF, relevés PDF, reçus PDF numérotés, rapport Excel.
- Comptabilité : dépenses et synthèse recettes/dépenses/solde.
- Gestion des stocks, fournisseurs, personnel et paie.
- Classement automatique par classe dans les bulletins (calcul de rang).
- Tableau de bord, journal d'audit et sauvegarde automatique au démarrage et à la fermeture.

## Données et sauvegardes
Base : `~/.cs_hagad/cs_hagad.db`
Sauvegardes : `~/.cs_hagad/sauvegardes/`
Copie manuelle :
```bash
cp ~/.cs_hagad/cs_hagad.db ~/cs_hagad_backup.db
```

## Notes importantes
- Les périodes sont des libellés libres : mois, T1/T2/T3, S1/S2 ou Année. Les notes doivent être saisies avec le libellé exact utilisé lors de l'édition.
- Les bulletins et relevés affichent un emplacement de signature et cachet, à faire signer physiquement. Le logo CS HAGAD est dessiné dans l'interface et dans les PDF.
- Les reçus reprennent le dernier paiement enregistré pour l'élève sélectionné.
- Les tableaux de bord et états financiers sont des synthèses de gestion. Faites valider les règles comptables, de paie et les modèles officiels par votre établissement.
- Les droits d'accès sont des permissions par onglet, à affiner avant mise en production.
- La sauvegarde est locale et déclenchée au démarrage/à la fermeture ; pour une sauvegarde quotidienne même si l'application est fermée, configurer cron.
