import { statik } from "./statik";

export async function loadIt() {
  const m = await import("@/lib/constants");
  return m;
}

function inner() {
  async function deeper() {
    return import("./db");
  }
  return deeper;
}

// import("./commented-out")
/* import("./block-commented") */

const modName = "./computed";
export async function nonLiteral() {
  return import(modName);
}

export async function alsoStatik() {
  return import("./statik");
}

export function decoy() {
  return myimport("./not-an-import") || registry.import("./also-not");
}
