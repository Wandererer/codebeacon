use actix_web::{web, App, HttpServer, HttpResponse, Responder};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct User {
    id: u32,
    name: String,
}

async fn get_users() -> impl Responder {
    HttpResponse::Ok().json(Vec::<User>::new())
}

async fn get_user(path: web::Path<u32>) -> impl Responder {
    HttpResponse::Ok().json(User { id: *path, name: "test".into() })
}

async fn create_user(user: web::Json<User>) -> impl Responder {
    HttpResponse::Created().json(user.into_inner())
}

async fn update_user(path: web::Path<u32>, user: web::Json<User>) -> impl Responder {
    HttpResponse::Ok().json(user.into_inner())
}

async fn delete_user(path: web::Path<u32>) -> impl Responder {
    HttpResponse::NoContent().finish()
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
            .route("/users", web::get().to(get_users))
            .route("/users/{id}", web::get().to(get_user))
            .route("/users", web::post().to(create_user))
            .route("/users/{id}", web::put().to(update_user))
            .route("/users/{id}", web::delete().to(delete_user))
    })
    .bind("0.0.0.0:8080")?
    .run()
    .await
}
