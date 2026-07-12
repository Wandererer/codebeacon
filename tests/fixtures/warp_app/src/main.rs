use serde::{Deserialize, Serialize};
use warp::Filter;

#[derive(Serialize, Deserialize)]
struct User {
    id: u32,
    name: String,
}

async fn health_check() -> Result<impl warp::Reply, warp::Rejection> {
    Ok(warp::reply::json(&"ok"))
}

async fn list_users() -> Result<impl warp::Reply, warp::Rejection> {
    Ok(warp::reply::json(&Vec::<User>::new()))
}

async fn get_user(id: u32) -> Result<impl warp::Reply, warp::Rejection> {
    Ok(warp::reply::json(&User { id, name: "test".into() }))
}

async fn create_user(body: User) -> Result<impl warp::Reply, warp::Rejection> {
    Ok(warp::reply::json(&body))
}

async fn get_stats() -> Result<impl warp::Reply, warp::Rejection> {
    Ok(warp::reply::json(&"stats"))
}

// A route factory that returns its filter as the block's tail expression —
// exercises correlation by the enclosing `block` rather than a `let`.
fn goodbye() -> impl Filter<Extract = (impl warp::Reply,), Error = warp::Rejection> + Clone {
    warp::path!("goodbye" / String)
        .map(|name| warp::reply::html(format!("Goodbye, {}!", name)))
}

#[tokio::main]
async fn main() {
    // Macro path with a closure handler: method-unknown, handler unresolved.
    let hello = warp::path!("hello" / String)
        .map(|name| warp::reply::html(format!("Hello, {}!", name)));

    let health = warp::path("health")
        .and(warp::get())
        .and_then(health_check);

    let users_list = warp::path("users")
        .and(warp::get())
        .and_then(list_users);

    let users_create = warp::path("users")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(create_user);

    let user_one = warp::path!("users" / u32)
        .and(warp::get())
        .and_then(get_user);

    // .and(warp::path(...)) composition inside one binding → concatenated path.
    let stats = warp::path("api")
        .and(warp::path("v1"))
        .and(warp::path("stats"))
        .and(warp::get())
        .and_then(get_stats);

    let routes = hello
        .or(goodbye())
        .or(health)
        .or(users_list)
        .or(users_create)
        .or(user_one)
        .or(stats);

    warp::serve(routes).run(([127, 0, 0, 1], 3030)).await;
}
