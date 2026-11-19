variable "project_id" {
  description = "Projet GCP dedie a ce pipeline (distinct de celui de Velib')."
  type        = string
}

# Pas de valeur par defaut : le choix de la region pese sur le cout (le free
# tier Cloud Storage n'existe que dans trois regions US). Il doit etre ecrit
# explicitement dans terraform.tfvars, pas herite en silence.
#
# Et il est quasi definitif : la region d'un dataset BigQuery ne peut plus
# etre changee apres sa creation.
variable "region" {
  description = "Region unique du bucket et des datasets. Un chargement depuis un bucket situe ailleurs reste possible, mais entraine des frais de transfert."
  type        = string
}

variable "landing_retention_days" {
  description = "Duree de vie du JSON brut dans le bucket de landing. A recalibrer apres mesure du volume reel (etape 6)."
  type        = number
  default     = 30
}

# true depuis le 18/11/2026 (image deposee, cle dans le coffre) : le code decrit
# ce qui existe. Sur un projet neuf, lancer d'abord avec
# -var deployer_le_job=false (le job ne peut pas naitre sans image ni cle).
variable "deployer_le_job" {
  description = "Deuxieme temps de job.tf : creer le job et le reveil. A passer a true seulement quand l'image est sur l'etagere et la cle Riot dans le coffre."
  type        = bool
  default     = true
}

# false depuis la bascule du 18/11/2026 : le DAG lol_daily du PC a ete mis en
# pause AVANT, pour qu'il n'y ait jamais deux collectes en meme temps.
variable "reveil_en_pause" {
  description = "Le reveil du job quotidien reste en pause tant que la bascule n'est pas faite (jamais deux collectes en meme temps)."
  type        = bool
  default     = false
}

# Pas de valeur par defaut : une adresse personnelle n'a rien a faire dans le
# code. Elle est dans terraform.tfvars, ignore par git.
variable "alerte_courriel" {
  description = "Adresse qui recoit le courriel quand le run quotidien echoue (alerte.tf)."
  type        = string
}

# 1 : 18/11/2026 (commit 194111e). 2 : 19/11/2026 (commit f705bdd : codes de
# vitesse d'attaque, critique et letalite dans le moteur theorique ; groupes
# d'objets charges). 3 : 19/11/2026 (regle "sans la survie" du moteur
# theorique). Revenir en arriere : remettre l'ancienne valeur et apply.
variable "job_image_tag" {
  description = "La version de l'image du job a lancer (etiquette sur l'etagere lol-job)."
  type        = string
  default     = "3"
}

variable "ladder_retention_days" {
  description = "Fenetre glissante des evenements de ladder dans BigQuery. Un patch dure environ deux semaines."
  type        = number
  default     = 60
}
