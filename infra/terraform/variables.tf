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

variable "ladder_retention_days" {
  description = "Fenetre glissante des evenements de ladder dans BigQuery. Un patch dure environ deux semaines."
  type        = number
  default     = 60
}
